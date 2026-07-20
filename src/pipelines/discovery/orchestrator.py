"""
SWASTHYA AI CORE — Discovery Pipeline Orchestrator.

Redesigned for Issues 6, 7, 8, 9:

Issue 6 — Progressive shortlisting:
    All search engines run → deduplicate → heuristic score → Top 8 → research → summarize → rank.
    We never scrape every candidate. Only shortlisted ones.

Issue 7 — Granular Redis progress updates:
    0%  → Queued
    10% → Planning Search
    25% → Google Places complete
    40% → Tavily complete
    50% → Deduplication complete
    65% → Research started
    80% → Research completed
    90% → Ranking hospitals
    100% → Completed
    Each stage updates Redis immediately.

Issue 8 — Graceful degradation:
    Each search source (NABH, Tavily, Maps) is wrapped independently.
    If any fails, the pipeline continues with remaining sources.
    If all sources return 0 results, the task fails gracefully with FAILED status.

Issue 9 — Explicit timeouts:
    Google Places: 8s
    Tavily: 12s
    NABH: 8s

The orchestrator receives a progress_callback that the worker provides.
This keeps the orchestrator pure while allowing the worker to control Redis updates.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Optional

from src.common.logging import get_logger
from src.domain.discovery.models import DiscoveryRequest, HospitalCandidate
from src.infrastructure.llm.gateway import LLMGateway
from src.pipelines.discovery.deduplicator import HospitalDeduplicator
from src.pipelines.discovery.facility_extractor import FacilityExtractor
from src.pipelines.discovery.gemini_summarizer import GeminiSummarizer
from src.pipelines.discovery.hospital_scraper import HospitalScraper
from src.pipelines.discovery.maps_search import GoogleMapsSearcher
from src.pipelines.discovery.nabh_search import NABHSearcher
from src.pipelines.discovery.normalizer import HospitalNormalizer
from src.pipelines.discovery.researcher import HospitalResearcher
from src.pipelines.discovery.review_extractor import ReviewExtractor
from src.pipelines.discovery.strategy import SearchStrategyGenerator
from src.pipelines.discovery.tavily_search import TavilySearcher
from src.pipelines.discovery.validator import HospitalValidator
from src.pipelines.discovery.resolver import HospitalEntityResolver

from src.config.settings import get_settings

logger = get_logger(__name__)

ProgressCallback = Callable[[int, str], Awaitable[None]]


class DiscoveryOrchestrator:
    """
    Orchestrates the progressive hospital discovery pipeline.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._strategy_gen = SearchStrategyGenerator(gateway)
        self._tavily = TavilySearcher()
        self._maps = GoogleMapsSearcher()
        self._nabh = NABHSearcher()
        self._scraper = HospitalScraper()
        self._resolver = HospitalEntityResolver()
        self._deduplicator = HospitalDeduplicator()
        self._normalizer = HospitalNormalizer()
        self._validator = HospitalValidator()
        self._researcher = HospitalResearcher(self._scraper)
        self._review_extractor = ReviewExtractor()
        self._facility_extractor = FacilityExtractor()
        self._summarizer = GeminiSummarizer(gateway)
        self._settings = get_settings()

    async def discover(
        self,
        request: DiscoveryRequest,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> list[HospitalCandidate]:
        """
        Execute the full progressive discovery pipeline.

        Args:
            request: The discovery request containing location, specialty etc.
            progress_callback: Optional async callback(percent, stage) for Redis updates.

        Returns:
            Final summarized HospitalCandidate list (max _SHORTLIST_SIZE).
        """

        async def _update(percent: int, stage: str) -> None:
            if progress_callback:
                try:
                    await progress_callback(percent, stage)
                except Exception as exc:
                    logger.warning("Progress callback failed", extra={"error": str(exc)})

        t_start = time.monotonic()
        t_stage = t_start
        task_id = request.task_id
        timings: dict[str, float] = {}

        def _record_timing(stage_name: str) -> None:
            nonlocal t_stage
            now = time.monotonic()
            timings[stage_name] = round((now - t_stage) * 1000, 1)
            t_stage = now

        logger.info(
            "Discovery pipeline started",
            extra={"task_id": task_id, "specialty": request.specialty.value},
        )

        # ── Stage: Planning Search (10%) ───────────────────────────────────────
        strategy = await self._strategy_gen.generate(request)
        _record_timing("planning")

        # ── Stage: Google Places Search (25%) ──────────────────────────────────
        await _update(25, "Searching")
        maps_candidates: list[HospitalCandidate] = []
        try:
            maps_candidates = await asyncio.wait_for(
                self._maps.search(strategy, request),
                timeout=self._settings.maps_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Google Maps search timed out", extra={"task_id": task_id})
        except Exception as exc:
            logger.warning("Google Maps search failed", extra={"task_id": task_id, "error": str(exc)})
        _record_timing("maps_search")

        # ── Stage: Tavily Search (40%) ─────────────────────────────────────────
        tavily_candidates: list[HospitalCandidate] = []
        try:
            tavily_candidates = await asyncio.wait_for(
                self._tavily.search(strategy, task_id),
                timeout=self._settings.tavily_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("Tavily search timed out", extra={"task_id": task_id})
        except Exception as exc:
            logger.warning("Tavily search failed", extra={"task_id": task_id, "error": str(exc)})
        _record_timing("tavily_search")

        # ── Stage: NABH Search (parallel, graceful degradation) ────────────────
        nabh_candidates: list[HospitalCandidate] = []
        try:
            nabh_candidates = await asyncio.wait_for(
                self._nabh.search(
                    city=request.location.city,
                    specialty=request.specialty.value,
                    task_id=task_id,
                ),
                timeout=self._settings.nabh_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("NABH search timed out", extra={"task_id": task_id})
        except Exception as exc:
            logger.warning("NABH search failed — continuing", extra={"task_id": task_id, "error": str(exc)})
        _record_timing("nabh_search")

        all_candidates = maps_candidates + tavily_candidates + nabh_candidates

        if not all_candidates:
            logger.warning(
                "No candidates found from any source",
                extra={
                    "task_id": task_id,
                    "maps": len(maps_candidates),
                    "tavily": len(tavily_candidates),
                    "nabh": len(nabh_candidates),
                },
            )
            return []

        # ── Stage: Entity Resolution (Phase 2) ─────────────────────────────────
        resolved_candidates = self._resolver.resolve_all(all_candidates, request.location.city)

        # ── Stage: Deduplication & Normalization (40%) ─────────────────────────
        unique_candidates = self._deduplicator.deduplicate(resolved_candidates)

        # ── Normalize (fills missing coordinates where possible) ───────────────
        normalized_candidates = await self._normalizer.normalize_all(
            unique_candidates, request.location.city
        )
        await _update(40, "Normalizing")

        # ── Stage: Validation (Quality Gate) ───────────────────────────────────
        valid_candidates = self._validator.validate_all(normalized_candidates)
        if not valid_candidates:
            logger.warning("No candidates passed the quality gate.", extra={"task_id": task_id})
            return []

        # ── Heuristic Shortlisting (Issue 6): top _SHORTLIST_SIZE only ─────────
        shortlisted = self._heuristic_shortlist(valid_candidates)

        logger.info(
            "Shortlisted candidates for research",
            extra={
                "task_id": task_id,
                "total": len(normalized_candidates),
                "shortlisted": len(shortlisted),
            },
        )

        # ── Stage: Research Shortlist (55%) ────────────────────────────────────
        await _update(55, "Research")

        # Heuristic signal extraction before expensive scraping
        shortlisted = self._review_extractor.extract_all(shortlisted)
        shortlisted = self._facility_extractor.extract_all(shortlisted)

        # Deep research: scrape only shortlisted hospitals (Issue 6)
        # return_exceptions=True inside researcher ensures single failures don't kill pipeline (Issue 3)
        researched = await self._researcher.research_all(shortlisted, task_id)
        _record_timing("research")

        # ── Stage: LLM Summarization ───────────────────────────────────────────
        final_candidates = await self._summarizer.summarize_all(researched, request)
        _record_timing("summarization")

        total_latency = int((time.monotonic() - t_start) * 1000)
        logger.info(
            "Discovery pipeline completed",
            extra={
                "task_id": task_id,
                "total_latency_ms": total_latency,
                "timings_ms": timings,
                "final_candidate_count": len(final_candidates),
            },
        )
        return final_candidates

    def _heuristic_shortlist(
        self,
        candidates: list[HospitalCandidate],
    ) -> list[HospitalCandidate]:
        """
        Score and shortlist candidates using fast heuristics before expensive scraping.

        Scoring signals (no LLM, instant):
        - Has coordinates: +3
        - Has website: +2
        - Has NABH accreditation: +3
        - Has overall_rating: +1 per star above 3.0
        - Has contact_number: +1
        - Source is Maps (most reliable): +2
        - Has emergency: +2
        """

        def _score(c: HospitalCandidate) -> float:
            score = 0.0
            if c.coordinates:
                score += 3.0
            if c.website:
                score += 2.0
            if "NABH" in c.accreditations:
                score += 3.0
            if c.overall_rating and c.overall_rating > 3.0:
                score += (c.overall_rating - 3.0)
            if c.contact_number:
                score += 1.0
            if c.source == "maps":
                score += 2.0
            if c.has_emergency:
                score += 2.0
            score += c.data_quality_score
            return score

        scored = sorted(candidates, key=_score, reverse=True)
        return scored[:self._settings.shortlist_size]

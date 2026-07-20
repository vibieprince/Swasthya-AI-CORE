"""
SWASTHYA AI CORE — Hospital Researcher.

Fixes applied (Issue 3, 6):
- Issue 3: asyncio.gather with return_exceptions=True — one failed scrape
  never kills the entire pipeline.
- Issue 6: Only researches the shortlisted top-N candidates, not all discovered
  candidates. Caller (orchestrator) passes pre-shortlisted list.
- Explicit 10-second timeout per scrape task (Issue 9).
- Graceful degradation: failed hospitals are retained without scrape data (Issue 8).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate
from src.pipelines.discovery.hospital_scraper import HospitalScraper

from src.config.settings import get_settings

logger = get_logger(__name__)


class HospitalResearcher:
    """
    Deep-researches a shortlisted set of hospital candidates by scraping their websites.

    Safe: one broken website never kills the pipeline.
    Efficient: only top-N shortlisted candidates are scraped.
    """

    def __init__(self, scraper: HospitalScraper) -> None:
        self._scraper = scraper
        self._settings = get_settings()

    async def research_all(
        self,
        candidates: list[HospitalCandidate],
        task_id: str,
    ) -> list[HospitalCandidate]:
        """
        Concurrently research all candidates.

        Uses asyncio.gather with return_exceptions=True (Issue 3).
        Failed scrapes are logged and the candidate is retained without data.
        """
        if not candidates:
            return []

        semaphore = asyncio.Semaphore(self._settings.research_concurrency)

        async def _research_safe(c: HospitalCandidate) -> HospitalCandidate:
            async with semaphore:
                try:
                    # Per-candidate timeout wrapper (Issue 9)
                    return await asyncio.wait_for(
                        self._research(c, task_id),
                        timeout=self._settings.research_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Research timed out for hospital",
                        extra={"hospital": c.hospital_name, "task_id": task_id},
                    )
                    return c  # Return without scrape data — graceful degradation (Issue 8)
                except Exception as exc:
                    logger.warning(
                        "Research failed for hospital — continuing",
                        extra={"hospital": c.hospital_name, "error": str(exc)[:150], "task_id": task_id},
                    )
                    return c  # Retain candidate even without scraped data (Issue 8)

        # return_exceptions=True ensures one failure cannot cancel siblings (Issue 3)
        results = await asyncio.gather(
            *[_research_safe(c) for c in candidates],
            return_exceptions=True,
        )

        researched: list[HospitalCandidate] = []
        for idx, result in enumerate(results):
            if isinstance(result, BaseException):
                # Defensive: _research_safe should never raise, but if it does
                # we keep the original candidate unmodified
                logger.error(
                    "Unexpected exception from _research_safe",
                    extra={"error": str(result), "task_id": task_id},
                )
                researched.append(candidates[idx])
            else:
                researched.append(result)

        scraped_count = sum(1 for c in researched if c.raw_scrape_data)
        logger.info(
            "Research phase completed",
            extra={
                "task_id": task_id,
                "total": len(researched),
                "scraped": scraped_count,
                "skipped": len(researched) - scraped_count,
            },
        )
        return researched

    async def _research(self, candidate: HospitalCandidate, task_id: str) -> HospitalCandidate:
        """Research a single candidate by scraping its website."""
        # Only skip scraping if we already have snippet data AND there is no
        # website URL to scrape. A Tavily snippet alone is insufficient —
        # it lacks structured data (phone, address, ICU flags, accreditations).
        if candidate.raw_scrape_data and not candidate.website:
            return candidate

        if not candidate.website:
            return candidate

        logger.info(
            "Scraping hospital website",
            extra={"hospital": candidate.hospital_name, "url": candidate.website, "task_id": task_id},
        )

        scraped_text = await self._scraper.scrape(candidate.website, task_id)
        if scraped_text:
            candidate.raw_scrape_data = scraped_text
            candidate.data_quality_score = min(1.0, candidate.data_quality_score + 0.1)

        return candidate

"""
SWASTHYA AI CORE — Gemini Summarizer.

Passes the raw collected data for each hospital through the LLM Gateway
to produce a structured, clinical summary of the hospital's capabilities.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.common.exceptions import DiscoveryPipelineError
from src.common.logging import get_logger
from src.common.prompts.discovery_prompts import (
    PROMPT_VERSION,
    SUMMARIZE_SYSTEM,
    SUMMARIZE_USER_TEMPLATE,
)
from src.domain.discovery.models import DiscoveryRequest, HospitalCandidate
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest

logger = get_logger(__name__)


class GeminiSummarizer:
    """
    Summarizes raw hospital data into structured clinical insights.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def summarize_all(
        self,
        candidates: list[HospitalCandidate],
        request: DiscoveryRequest,
    ) -> list[HospitalCandidate]:
        """Summarize all candidates concurrently."""
        semaphore = asyncio.Semaphore(4)

        async def _summarize_one(c: HospitalCandidate) -> HospitalCandidate:
            async with semaphore:
                return await self._summarize(c, request)

        summarized = await asyncio.gather(*[_summarize_one(c) for c in candidates])
        return list(summarized)

    async def _summarize(
        self,
        candidate: HospitalCandidate,
        request: DiscoveryRequest,
    ) -> HospitalCandidate:
        """Summarize a single hospital candidate."""
        # Combine all known data into a raw text representation for the LLM
        raw_data = (
            f"Name: {candidate.hospital_name}\n"
            f"Address: {candidate.raw_address}\n"
            f"Phone: {candidate.contact_number}\n"
            f"Website: {candidate.website}\n"
            f"Rating: {candidate.overall_rating} ({candidate.review_count} reviews)\n"
            f"Accreditations known: {', '.join(candidate.accreditations)}\n"
            f"Emergency known: {candidate.has_emergency}\n"
            f"ICU known: {candidate.has_icu}\n"
            f"Raw Extracted Text: {candidate.raw_scrape_data[:3000] if candidate.raw_scrape_data else 'None'}\n"
        )

        llm_request = LLMRequest(
            system_prompt=SUMMARIZE_SYSTEM,
            user_prompt=SUMMARIZE_USER_TEMPLATE.format(
                hospital_name=candidate.hospital_name,
                raw_data=raw_data,
                specialty=request.specialty.value,
                budget_preference=request.budget_preference.value,
                urgency=request.urgency.value,
            ),
            temperature=0.1,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(llm_request, pipeline_stage="discovery_summarize")
            p = response.parsed
            
            # Merge LLM insights into the candidate
            candidate.hospital_type = p.get("hospital_type", candidate.hospital_type)
            
            for acc in p.get("accreditations", []):
                if acc not in candidate.accreditations:
                    candidate.accreditations.append(acc)
                    
            candidate.specialties = list(set(candidate.specialties + p.get("specialties_available", [])))
            
            if candidate.has_emergency is None:
                candidate.has_emergency = p.get("has_emergency")
            if candidate.has_icu is None:
                candidate.has_icu = p.get("has_icu")
                
            cost_range = p.get("estimated_cost_range", {})
            if not candidate.estimated_cost_min_inr:
                candidate.estimated_cost_min_inr = cost_range.get("min_inr")
            if not candidate.estimated_cost_max_inr:
                candidate.estimated_cost_max_inr = cost_range.get("max_inr")
                
            candidate.key_strengths = list(set(candidate.key_strengths + p.get("key_strengths", [])))
            candidate.known_limitations = list(set(candidate.known_limitations + p.get("known_limitations", [])))
            candidate.clinical_notes = p.get("clinical_notes")
            
            # Blend the LLM's data quality score with the existing one
            llm_dq = float(p.get("data_quality_score", 0.5))
            candidate.data_quality_score = (candidate.data_quality_score + llm_dq) / 2.0

        except Exception as exc:
            logger.warning(
                "Gemini summarization failed for candidate",
                extra={"hospital": candidate.hospital_name, "error": str(exc)},
            )
            # If summarization fails, we still keep the candidate with heuristics data

        return candidate

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
        """Summarize all candidates in a single batched LLM call."""
        if not candidates:
            return []

        # Build raw data string for all candidates
        batch_raw_data = ""
        for c in candidates:
            batch_raw_data += (
                f"CANDIDATE ID: {c.candidate_id}\n"
                f"Name: {c.hospital_name}\n"
                f"Address: {c.raw_address}\n"
                f"Phone: {c.contact_number}\n"
                f"Website: {c.website}\n"
                f"Rating: {c.overall_rating} ({c.review_count} reviews)\n"
                f"Accreditations known: {', '.join(c.accreditations)}\n"
                f"Emergency known: {c.has_emergency}\n"
                f"ICU known: {c.has_icu}\n"
                f"Raw Extracted Text: {c.raw_scrape_data[:3000] if c.raw_scrape_data else 'None'}\n"
                f"---------------------------------------------------\n"
            )

        llm_request = LLMRequest(
            system_prompt=SUMMARIZE_SYSTEM,
            user_prompt=SUMMARIZE_USER_TEMPLATE.format(
                batch_raw_data=batch_raw_data,
                specialty=request.specialty.value,
                budget_preference=request.budget_preference.value,
                urgency=request.urgency.value,
            ),
            temperature=0.1,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(llm_request, pipeline_stage="discovery_summarize")
            batch_parsed = response.parsed
            
            for c in candidates:
                p = batch_parsed.get(c.candidate_id, {})
                if not p:
                    continue
                    
                c.hospital_type = p.get("hospital_type", c.hospital_type)
                
                for acc in p.get("accreditations", []):
                    if acc not in c.accreditations:
                        c.accreditations.append(acc)
                        
                c.specialties = list(set(c.specialties + p.get("specialties_available", [])))
                
                if c.has_emergency is None:
                    c.has_emergency = p.get("has_emergency")
                if c.has_icu is None:
                    c.has_icu = p.get("has_icu")
                    
                cost_range = p.get("estimated_cost_range", {})
                if not c.estimated_cost_min_inr:
                    c.estimated_cost_min_inr = cost_range.get("min_inr")
                if not c.estimated_cost_max_inr:
                    c.estimated_cost_max_inr = cost_range.get("max_inr")
                    
                c.key_strengths = list(set(c.key_strengths + p.get("key_strengths", [])))
                c.known_limitations = list(set(c.known_limitations + p.get("known_limitations", [])))
                c.clinical_notes = p.get("clinical_notes")
                
                # Blend the LLM's data quality score
                llm_dq = float(p.get("data_quality_score", 0.5))
                c.data_quality_score = (c.data_quality_score + llm_dq) / 2.0

        except Exception as exc:
            logger.warning(
                "Gemini batch summarization failed",
                extra={"error": str(exc)},
            )
            # If summarization fails, we still keep candidates with heuristics data

        return candidates

"""
SWASTHYA AI CORE — Recommendation Explainer.

Uses the LLM Gateway to generate human-readable, patient-friendly 
explanations for why each hospital was ranked at its specific position.
"""

from __future__ import annotations

import asyncio

from src.common.exceptions import DiscoveryPipelineError
from src.common.logging import get_logger
from src.common.prompts.discovery_prompts import (
    EXPLAIN_SYSTEM,
    EXPLAIN_USER_TEMPLATE,
    PROMPT_VERSION,
)
from src.domain.discovery.models import DiscoveryRequest
from src.domain.ranking.models import RankedHospital
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest

logger = get_logger(__name__)


class RecommendationExplainer:
    """
    Generates explainable AI insights for each ranked recommendation.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def explain_all(
        self,
        ranked_hospitals: list[RankedHospital],
        request: DiscoveryRequest,
    ) -> list[RankedHospital]:
        """Generate explanations for all ranked hospitals in a single batched LLM call."""
        
        if not ranked_hospitals:
            return []

        total_ranked = len(ranked_hospitals)
        batch_ranking_data = ""
        
        for h in ranked_hospitals:
            batch_ranking_data += (
                f"HOSPITAL NAME: {h.hospital_name}\n"
                f"Rank: {h.rank} of {total_ranked}\n"
                f"Overall Score: {round(h.overall_score, 2)}\n"
                f"Key Strengths: {', '.join(h.pros)}\n"
                f"Known Limitations: {', '.join(h.cons)}\n"
                f"---------------------------------------------------\n"
            )

        llm_request = LLMRequest(
            system_prompt=EXPLAIN_SYSTEM,
            user_prompt=EXPLAIN_USER_TEMPLATE.format(
                batch_ranking_data=batch_ranking_data,
                specialty=request.specialty.value,
                language_code=request.language_code,
            ),
            temperature=0.2,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(llm_request, pipeline_stage="ranking_explain")
            batch_parsed = response.parsed
            
            for h in ranked_hospitals:
                p = batch_parsed.get(h.hospital_name, {})
                if not p:
                    # Fallback if omitted by LLM
                    h.summary = f"Recommended based on clinical suitability for {request.specialty.value}."
                    continue
                    
                h.summary = p.get("summary", "")
                
                if p.get("pros"):
                    h.pros = p.get("pros")
                    
                if p.get("cons"):
                    h.cons = p.get("cons")

        except Exception as exc:
            logger.warning(
                "Failed to generate batch explanations",
                extra={"error": str(exc)},
            )
            # Fallback text if explanation fails entirely
            for h in ranked_hospitals:
                h.summary = f"Recommended based on clinical suitability for {request.specialty.value}."

        return ranked_hospitals

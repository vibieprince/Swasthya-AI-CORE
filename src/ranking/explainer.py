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
                f"Name: {h.hospital_name}\n"
                f"Rank: {h.rank} of {total_ranked}\n"
                f"Trust Score: {round(h.scores.trust_score, 2)}\n"
                f"Clinical Suitability: {round(h.scores.clinical_suitability_score, 2)}\n"
                f"Affordability Score: {round(h.scores.affordability_score, 2)}\n"
                f"Key Strengths: {', '.join(h.top_reasons)}\n"
                f"Known Limitations: {', '.join(h.cautions)}\n"
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
                    h.recommendation_summary = f"Recommended based on clinical suitability for {request.specialty.value}."
                    h.recommendation_summary_english = h.recommendation_summary
                    h.why_this_rank = f"Ranked #{h.rank} based on overall match."
                    h.confidence_explanation = "Based on available data."
                    continue
                    
                h.recommendation_summary = p.get("recommendation_summary", "")
                h.recommendation_summary_english = p.get("recommendation_summary_english", "")
                h.why_this_rank = p.get("why_this_rank", "")
                
                if p.get("top_reasons"):
                    h.top_reasons = p.get("top_reasons")
                    
                if p.get("cautions"):
                    h.cautions = p.get("cautions")
                    
                h.confidence_explanation = p.get("confidence_explanation", "")

        except Exception as exc:
            logger.warning(
                "Failed to generate batch explanations",
                extra={"error": str(exc)},
            )
            # Fallback text if explanation fails entirely
            for h in ranked_hospitals:
                h.recommendation_summary = f"Recommended based on clinical suitability for {request.specialty.value}."
                h.recommendation_summary_english = h.recommendation_summary
                h.why_this_rank = f"Ranked #{h.rank} based on overall match."
                h.confidence_explanation = "Based on available data."

        return ranked_hospitals

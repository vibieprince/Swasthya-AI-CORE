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
        """Generate explanations for all ranked hospitals concurrently."""
        
        if not ranked_hospitals:
            return []

        total_ranked = len(ranked_hospitals)
        semaphore = asyncio.Semaphore(4)

        async def _explain_one(hospital: RankedHospital) -> RankedHospital:
            async with semaphore:
                return await self._explain(hospital, total_ranked, request)

        explained = await asyncio.gather(*[_explain_one(h) for h in ranked_hospitals])
        return list(explained)

    async def _explain(
        self,
        hospital: RankedHospital,
        total_ranked: int,
        request: DiscoveryRequest,
    ) -> RankedHospital:
        """Generate explanation for a single ranked hospital."""

        llm_request = LLMRequest(
            system_prompt=EXPLAIN_SYSTEM,
            user_prompt=EXPLAIN_USER_TEMPLATE.format(
                hospital_name=hospital.hospital_name,
                rank=hospital.rank,
                total_ranked=total_ranked,
                trust_score=round(hospital.scores.trust_score, 2),
                clinical_suitability=round(hospital.scores.clinical_suitability_score, 2),
                affordability_score=round(hospital.scores.affordability_score, 2),
                key_strengths=", ".join(hospital.top_reasons),
                known_limitations=", ".join(hospital.cautions),
                specialty=request.specialty.value,
                language_code=request.language_code,
            ),
            temperature=0.2,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(llm_request, pipeline_stage="ranking_explain")
            p = response.parsed
            
            hospital.recommendation_summary = p.get("recommendation_summary", "")
            hospital.recommendation_summary_english = p.get("recommendation_summary_english", "")
            hospital.why_this_rank = p.get("why_this_rank", "")
            
            if p.get("top_reasons"):
                hospital.top_reasons = p.get("top_reasons")
                
            if p.get("cautions"):
                hospital.cautions = p.get("cautions")
                
            hospital.confidence_explanation = p.get("confidence_explanation", "")

        except Exception as exc:
            logger.warning(
                "Failed to generate explanation for hospital",
                extra={"hospital": hospital.hospital_name, "error": str(exc)},
            )
            # Fallback text if explanation fails
            hospital.recommendation_summary = f"Recommended based on clinical suitability for {request.specialty.value}."
            hospital.recommendation_summary_english = hospital.recommendation_summary
            hospital.why_this_rank = f"Ranked #{hospital.rank} based on overall match."
            hospital.confidence_explanation = "Based on available data."

        return hospital

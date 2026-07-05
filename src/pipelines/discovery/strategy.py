"""
SWASTHYA AI CORE — Search Strategy Generator.

Generates a multi-source search strategy for hospital discovery
using the LLM Gateway.
"""

from __future__ import annotations

from src.common.exceptions import DiscoveryPipelineError
from src.common.logging import get_logger
from src.common.prompts.discovery_prompts import PROMPT_VERSION, STRATEGY_SYSTEM, STRATEGY_USER_TEMPLATE
from src.domain.discovery.models import DiscoveryRequest, SearchStrategy
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest

logger = get_logger(__name__)


class SearchStrategyGenerator:
    """Generates a clinical search strategy using the LLM gateway."""

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def generate(self, request: DiscoveryRequest) -> SearchStrategy:
        """
        Generate a hospital search strategy from the discovery request.

        Returns:
            SearchStrategy with queries, filters, and search depth.
        """
        loc = request.location
        location_text = loc.city
        if loc.state:
            location_text += f", {loc.state}"

        llm_request = LLMRequest(
            system_prompt=STRATEGY_SYSTEM,
            user_prompt=STRATEGY_USER_TEMPLATE.format(
                specialty=request.specialty.value,
                location=location_text,
                urgency=request.urgency.value,
                budget_preference=request.budget_preference.value,
                hospital_type=request.hospital_type_preference.value,
                is_emergency=request.is_emergency,
            ),
            temperature=0.1,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(llm_request, pipeline_stage="discovery_strategy")
        except Exception as exc:
            raise DiscoveryPipelineError(
                stage="strategy_generation",
                message=f"LLM failed to generate search strategy: {exc}",
            ) from exc

        p = response.parsed
        try:
            strategy = SearchStrategy(
                primary_search_queries=p.get("primary_search_queries", []),
                nabh_search_terms=p.get("nabh_search_terms", []),
                specialty_keywords=p.get("specialty_keywords", []),
                location_variants=p.get("location_variants", [location_text]),
                search_radius_km=int(p.get("search_radius_km", 25)),
                priority_filters=p.get("priority_filters", {}),
                search_depth=p.get("search_depth", "standard"),
            )
        except Exception as exc:
            raise DiscoveryPipelineError(
                stage="strategy_generation",
                message=f"Failed to parse strategy response: {exc}",
            ) from exc

        logger.info(
            "Search strategy generated",
            extra={
                "task_id": request.task_id,
                "query_count": len(strategy.primary_search_queries),
                "search_depth": strategy.search_depth,
            },
        )
        return strategy

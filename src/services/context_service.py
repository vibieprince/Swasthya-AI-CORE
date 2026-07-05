"""
SWASTHYA AI CORE — Context Service.

Application service layer for Context Intelligence.
Maps DTOs to Domain objects and calls the orchestrator.
"""

from __future__ import annotations

from src.common.exceptions import SwasthyaBaseError
from src.common.logging import get_logger
from src.dtos.context_dtos import ContextAnalyzeRequest, ContextAnalyzeResponse
from src.pipelines.context.orchestrator import ContextOrchestrator

logger = get_logger(__name__)


class ContextService:
    """
    Service for the Context Intelligence API.
    """

    def __init__(self, orchestrator: ContextOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def analyze_context(self, request: ContextAnalyzeRequest) -> ContextAnalyzeResponse:
        """
        Run the context pipeline and return the mapped DTO.
        """
        logger.info("Handling context analyze request")

        try:
            patient_context = await self._orchestrator.run(request.message)
            return ContextAnalyzeResponse.from_domain(patient_context)
        except SwasthyaBaseError:
            raise
        except Exception as exc:
            logger.error("Unhandled error in ContextService", extra={"error": str(exc)})
            raise SwasthyaBaseError("An unexpected error occurred during context analysis.") from exc

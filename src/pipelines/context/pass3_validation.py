"""
SWASTHYA AI CORE — Context Pipeline Pass 3.

Validates extracted context for completeness and generates a targeted
follow-up question when minimum requirements are not met.
"""

from __future__ import annotations

import time
from typing import Optional

from src.common.exceptions import ContextPipelineError
from src.common.logging import get_logger
from src.common.prompts.context_prompts import (
    PASS3_SYSTEM,
    PASS3_USER_TEMPLATE,
    PROMPT_VERSION,
)
from src.domain.context.models import ClinicalData, ContextValidation, MissingField
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest

logger = get_logger(__name__)


class Pass3Validator:
    """
    Context Pipeline Pass 3.

    Validates that extracted clinical context meets the minimum threshold
    for high-quality hospital discovery. If the threshold is not met,
    generates a single, targeted follow-up question in the patient's language.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def run(
        self,
        clinical: ClinicalData,
        language_code: str,
        intent: str,
        missing_field: MissingField,
    ) -> ContextValidation:
        """Execute Pass 3 validation and follow-up generation."""
        t_start = time.monotonic()

        request = LLMRequest(
            system_prompt=PASS3_SYSTEM,
            user_prompt=PASS3_USER_TEMPLATE.format(
                language_code=language_code,
                intent=intent,
                missing_field=missing_field.display_name,
            ),
            temperature=0.05,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(request, pipeline_stage="context_pass3")
        except Exception as exc:
            raise ContextPipelineError(
                stage="pass3_validation",
                message=f"LLM gateway failed in Pass 3: {exc}",
            ) from exc

        p = response.parsed
        latency_ms = int((time.monotonic() - t_start) * 1000)

        try:
            validation = ContextValidation(
                is_context_sufficient=False,
                missing_fields=[missing_field.id],
                needs_followup=True,
                followup_question=p.get("followup_question"),
                followup_question_english=p.get("followup_question_english"),
                context_confidence=1.0,
                validation_notes="Missing required fields deterministically identified.",
            )
        except Exception as exc:
            raise ContextPipelineError(
                stage="pass3_validation",
                message=f"Failed to parse Pass 3 LLM response: {exc}",
            ) from exc

        logger.info(
            "Pass 3 completed (LLM Follow-up)",
            extra={
                "is_sufficient": validation.is_context_sufficient,
                "needs_followup": validation.needs_followup,
                "missing_count": len(validation.missing_fields),
                "confidence": validation.context_confidence,
                "latency_ms": latency_ms,
            },
        )
        return validation

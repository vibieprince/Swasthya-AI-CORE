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
from src.domain.context.models import ClinicalData, ContextValidation
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
    ) -> ContextValidation:
        """
        Execute Pass 3 validation and optional follow-up generation.

        Args:
            clinical: Extracted ClinicalData from Pass 2.
            language_code: Patient's detected language.
            intent: Detected clinical intent string.

        Returns:
            ContextValidation with sufficiency flag and optional follow-up question.

        Raises:
            ContextPipelineError: On LLM failure or parse error.
        """
        t_start = time.monotonic()

        # ── Deterministic Validation (Pure Python) ────────────────────────────
        missing = []
        if not clinical.symptoms:
            missing.append("symptoms")
        
        # If it's an emergency, we don't block on location/budget
        if not clinical.is_emergency:
            if not clinical.patient_location.city and not clinical.patient_location.raw_location:
                missing.append("location")
            if not clinical.preferred_specialty and not clinical.symptoms:
                missing.append("specialty_or_symptoms")
        
        # Is the context sufficient for discovery?
        is_sufficient = len(missing) == 0

        # If sufficient, skip the LLM call entirely (saves ~3 seconds)
        if is_sufficient:
            latency_ms = int((time.monotonic() - t_start) * 1000)
            logger.info(
                "Pass 3 completed (Deterministic fast-path)",
                extra={
                    "is_sufficient": True,
                    "needs_followup": False,
                    "missing_count": 0,
                    "confidence": 0.95,
                    "latency_ms": latency_ms,
                },
            )
            return ContextValidation(
                is_context_sufficient=True,
                missing_fields=[],
                needs_followup=False,
                followup_question=None,
                followup_question_english=None,
                context_confidence=0.95,
                validation_notes="Context is sufficient. Skipped LLM validation.",
            )

        # ── LLM Fallback (Only when follow-up is needed) ──────────────────────
        request = LLMRequest(
            system_prompt=PASS3_SYSTEM,
            user_prompt=PASS3_USER_TEMPLATE.format(
                language_code=language_code,
                intent=intent,
                symptoms_count=len(clinical.symptoms),
                has_location=clinical.patient_location.city is not None,
                has_budget=clinical.budget.max_inr is not None or clinical.budget.preference != "any",
                urgency=clinical.urgency_level.value,
                is_emergency=clinical.is_emergency,
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
                is_context_sufficient=False,  # Enforce deterministic failure
                missing_fields=missing,
                needs_followup=True,
                followup_question=p.get("followup_question"),
                followup_question_english=p.get("followup_question_english"),
                context_confidence=float(p.get("context_confidence", 0.5)),
                validation_notes=p.get("validation_notes", ""),
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

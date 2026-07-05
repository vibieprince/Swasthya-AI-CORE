"""
SWASTHYA AI CORE — Context Pipeline Orchestrator.

Wires Pass 1 → Pass 2 → Pass 3 with short-circuit logic for greetings
and irrelevant messages.
"""

from __future__ import annotations

import time
import uuid

from src.common.exceptions import ContextPipelineError
from src.common.logging import get_logger
from src.common.prompts.context_prompts import GREETING_SYSTEM, GREETING_USER_TEMPLATE, PROMPT_VERSION
from src.domain.context.enums import ClinicalIntent
from src.domain.context.models import (
    ClinicalData,
    ContextValidation,
    LanguageIntelligence,
    PatientContext,
)
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest
from src.pipelines.context.pass1_language_intent import Pass1LanguageIntentDetector
from src.pipelines.context.pass2_clinical import Pass2ClinicalExtractor
from src.pipelines.context.pass3_validation import Pass3Validator

logger = get_logger(__name__)


class ContextOrchestrator:
    """
    Orchestrates the three-pass context intelligence pipeline.

    Routing logic:
    - Greeting      → Pass 1 only, generate greeting response
    - Irrelevant    → Pass 1 only, return insufficient context
    - Healthcare    → Pass 1 → Pass 2 → Pass 3

    Injects the LLM gateway into each pass.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway
        self._pass1 = Pass1LanguageIntentDetector(gateway)
        self._pass2 = Pass2ClinicalExtractor(gateway)
        self._pass3 = Pass3Validator(gateway)

    async def run(self, message: str) -> PatientContext:
        """
        Execute the full context intelligence pipeline.

        Args:
            message: Raw patient message (any language).

        Returns:
            PatientContext — the complete, validated patient context.

        Raises:
            ContextPipelineError: On unrecoverable pipeline failure.
        """
        t_pipeline_start = time.monotonic()
        context_id = str(uuid.uuid4())

        # ── Pass 1: Language + Intent ─────────────────────────────────────────
        language: LanguageIntelligence = await self._pass1.run(message)

        # ── Short-circuit: Greeting ───────────────────────────────────────────
        if language.is_greeting:
            greeting_response = await self._generate_greeting(
                language.language_code,
                language.language_name,
            )
            return PatientContext(
                context_id=context_id,
                language=language,
                clinical=ClinicalData(),
                validation=ContextValidation(
                    is_context_sufficient=False,
                    needs_followup=True,
                    followup_question=greeting_response,
                    context_confidence=1.0,
                    validation_notes="Greeting detected — no clinical context yet.",
                ),
                raw_message=message,
                processing_latency_ms=int((time.monotonic() - t_pipeline_start) * 1000),
            )

        # ── Short-circuit: Irrelevant ─────────────────────────────────────────
        if language.is_irrelevant:
            return PatientContext(
                context_id=context_id,
                language=language,
                clinical=ClinicalData(),
                validation=ContextValidation(
                    is_context_sufficient=False,
                    needs_followup=False,
                    context_confidence=1.0,
                    validation_notes="Irrelevant query — not a healthcare request.",
                ),
                raw_message=message,
                processing_latency_ms=int((time.monotonic() - t_pipeline_start) * 1000),
            )

        # ── Pass 2: Clinical Extraction ───────────────────────────────────────
        clinical: ClinicalData = await self._pass2.run(
            message=message,
            language_code=language.language_code,
            intent=language.detected_intent,
        )

        # ── Pass 3: Validation + Follow-up ────────────────────────────────────
        validation: ContextValidation = await self._pass3.run(
            clinical=clinical,
            language_code=language.language_code,
            intent=language.detected_intent.value,
        )

        total_latency_ms = int((time.monotonic() - t_pipeline_start) * 1000)

        logger.info(
            "Context pipeline completed",
            extra={
                "context_id": context_id,
                "language": language.language_code,
                "intent": language.detected_intent.value,
                "is_sufficient": validation.is_context_sufficient,
                "needs_followup": validation.needs_followup,
                "total_latency_ms": total_latency_ms,
            },
        )

        return PatientContext(
            context_id=context_id,
            language=language,
            clinical=clinical,
            validation=validation,
            raw_message=message,
            processing_latency_ms=total_latency_ms,
        )

    async def _generate_greeting(
        self,
        language_code: str,
        language_name: str,
    ) -> str:
        """Generate a warm, language-appropriate greeting message."""
        try:
            request = LLMRequest(
                system_prompt=GREETING_SYSTEM,
                user_prompt=GREETING_USER_TEMPLATE.format(
                    language_code=language_code,
                    language_name=language_name,
                ),
                temperature=0.3,
                prompt_version=PROMPT_VERSION,
            )
            response = await self._gateway.complete(request, pipeline_stage="context_greeting")
            return str(response.parsed.get("greeting_message", "Hello! How can I help you today?"))
        except Exception:
            return "Hello! Please describe your health concern and we'll find the best hospitals for you."

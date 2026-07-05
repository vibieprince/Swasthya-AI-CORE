"""
SWASTHYA AI CORE — Context Pipeline Pass 1.

Detects language, intent, and whether the message is a greeting.
This is the lightest pass — it runs first and determines pipeline routing.
"""

from __future__ import annotations

import time

from src.common.exceptions import ContextPipelineError
from src.common.logging import get_logger
from src.common.prompts.context_prompts import (
    PASS1_SYSTEM,
    PASS1_USER_TEMPLATE,
    PROMPT_VERSION,
)
from src.domain.context.enums import ClinicalIntent
from src.domain.context.models import LanguageIntelligence
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest

logger = get_logger(__name__)


class Pass1LanguageIntentDetector:
    """
    Context Pipeline Pass 1.

    Responsibilities:
    - Detect the language of the patient's message
    - Classify the clinical intent
    - Detect greeting messages to short-circuit the pipeline
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def run(self, message: str) -> LanguageIntelligence:
        """
        Execute Pass 1 analysis.

        Args:
            message: The raw patient message.

        Returns:
            LanguageIntelligence with language code, intent, and greeting flag.

        Raises:
            ContextPipelineError: If the LLM gateway fails.
        """
        t_start = time.monotonic()

        request = LLMRequest(
            system_prompt=PASS1_SYSTEM,
            user_prompt=PASS1_USER_TEMPLATE.format(message=message),
            temperature=0.05,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(request, pipeline_stage="context_pass1")
        except Exception as exc:
            raise ContextPipelineError(
                stage="pass1_language_intent",
                message=f"LLM gateway failed in Pass 1: {exc}",
            ) from exc

        parsed = response.parsed
        latency_ms = int((time.monotonic() - t_start) * 1000)

        try:
            intelligence = LanguageIntelligence(
                language_code=parsed.get("language_code", "en"),
                language_name=parsed.get("language_name", "English"),
                is_greeting=bool(parsed.get("is_greeting", False)),
                is_healthcare_query=bool(parsed.get("is_healthcare_query", True)),
                is_irrelevant=bool(parsed.get("is_irrelevant", False)),
                detected_intent=ClinicalIntent(
                    parsed.get("detected_intent", ClinicalIntent.FIND_HOSPITAL.value)
                ),
                confidence=float(parsed.get("confidence", 0.8)),
                reasoning=parsed.get("reasoning", ""),
            )
        except (KeyError, ValueError) as exc:
            raise ContextPipelineError(
                stage="pass1_language_intent",
                message=f"Failed to parse Pass 1 LLM response: {exc}",
            ) from exc

        logger.info(
            "Pass 1 completed",
            extra={
                "language": intelligence.language_code,
                "intent": intelligence.detected_intent.value,
                "is_greeting": intelligence.is_greeting,
                "latency_ms": latency_ms,
            },
        )
        return intelligence

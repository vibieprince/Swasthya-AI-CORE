"""
SWASTHYA AI CORE — Multi-Provider LLM Gateway.

This is the SINGLE entry point for all LLM calls throughout the system.
No pipeline may call Gemini or Mistral directly.

Failover behaviour:
    1. Attempt Gemini up to gemini_max_retries times with exponential backoff.
    2. On exhaustion, automatically switch to Mistral.
    3. Attempt Mistral up to mistral_max_retries times.
    4. If both providers fail, raise LLMGatewayExhaustedError.

This behaviour is completely transparent to calling code.
"""

from __future__ import annotations

import asyncio
import time

from src.common.exceptions import (
    LLMGatewayExhaustedError,
    LLMInvalidResponseError,
    LLMProviderError,
)
from src.common.logging import get_logger
from src.config.settings import get_settings
from src.infrastructure.llm.providers.base import BaseLLMProvider, LLMRequest, LLMResponse
from src.infrastructure.llm.providers.gemini import GeminiProvider
from src.infrastructure.llm.providers.mistral import MistralProvider
from src.infrastructure.llm.telemetry import emit_failure_telemetry, emit_telemetry

logger = get_logger(__name__)


class LLMGateway:
    """
    Resilient multi-provider LLM gateway.

    Transparently routes all requests through Gemini with automatic
    failover to Mistral on any provider-level failure.

    Instantiate once and inject as a singleton dependency.
    """

    def __init__(
        self,
        primary: BaseLLMProvider | None = None,
        secondary: BaseLLMProvider | None = None,
    ) -> None:
        self._primary: BaseLLMProvider = primary or GeminiProvider()
        self._secondary: BaseLLMProvider = secondary or MistralProvider()
        settings = get_settings()
        
        # ── Circuit Breaker State ──────────────────────────────────────────────
        self._consecutive_failures = 0
        self._cooldown_until = 0.0
        self._lock = asyncio.Lock()
        self._failure_threshold = settings.llm_circuit_breaker_threshold
        self._cooldown_duration_sec = float(settings.llm_circuit_breaker_cooldown)

    async def complete(
        self,
        request: LLMRequest,
        pipeline_stage: str = "unknown",
    ) -> LLMResponse:
        """
        Execute an LLM completion with automatic failover.

        Args:
            request: The normalised LLM request.
            pipeline_stage: Identifier for telemetry (e.g., "context_pass1").

        Returns:
            LLMResponse from whichever provider succeeded.

        Raises:
            LLMGatewayExhaustedError: If all providers and retries are exhausted.
        """
        t_start = time.monotonic()

        # ── Check Circuit Breaker ──────────────────────────────────────────────
        if t_start < self._cooldown_until:
            # Circuit is open — skip primary entirely
            logger.warning(
                "Circuit breaker OPEN — skipping primary provider",
                extra={
                    "primary_provider": self._primary.provider_name,
                    "pipeline_stage": pipeline_stage,
                    "cooldown_remaining": round(self._cooldown_until - t_start, 1)
                }
            )
            return await self._execute_secondary(request, pipeline_stage, t_start, "Circuit Breaker OPEN")

        # ── Attempt Primary (Gemini) ───────────────────────────────────────────
        try:
            response = await self._primary.complete(request)
            emit_telemetry(response, pipeline_stage)
            logger.info(
                "LLM request completed",
                extra={
                    "provider": response.provider,
                    "model": response.model,
                    "latency_ms": response.latency_ms,
                    "pipeline_stage": pipeline_stage,
                    "failover": False,
                },
            )
            # Reset circuit breaker on success
            if self._consecutive_failures > 0:
                async with self._lock:
                    self._consecutive_failures = 0

            return response

        except (LLMProviderError, LLMInvalidResponseError) as primary_exc:
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            failover_reason = (
                f"{type(primary_exc).__name__}: {primary_exc.message}"
                if hasattr(primary_exc, "message")
                else str(primary_exc)
            )
            
            # Trip circuit breaker
            async with self._lock:
                self._consecutive_failures += 1
                
                # Fast-trip circuit breaker on 429 (Rate Limited) to avoid hammering
                is_rate_limit = getattr(primary_exc, "status_code", None) == 429
                
                if self._consecutive_failures >= self._failure_threshold or is_rate_limit:
                    self._cooldown_until = time.monotonic() + self._cooldown_duration_sec
                    logger.error(
                        "Circuit breaker TRIPPED",
                        extra={
                            "provider": self._primary.provider_name,
                            "threshold": self._failure_threshold,
                            "cooldown_seconds": self._cooldown_duration_sec,
                            "is_rate_limit_fast_trip": is_rate_limit,
                        }
                    )

            logger.warning(
                "Primary LLM provider failed — activating failover",
                extra={
                    "primary_provider": self._primary.provider_name,
                    "failover_provider": self._secondary.provider_name,
                    "reason": failover_reason,
                    "elapsed_ms": elapsed_ms,
                    "pipeline_stage": pipeline_stage,
                },
            )
            
            return await self._execute_secondary(request, pipeline_stage, t_start, failover_reason)

    async def _execute_secondary(
        self,
        request: LLMRequest,
        pipeline_stage: str,
        t_start: float,
        failover_reason: str,
    ) -> LLMResponse:
        """Execute the secondary provider and handle its failures."""
        try:
            response = await self._secondary.complete(request)
            # Annotate the response with failover metadata
            response.failover_triggered = True
            response.failover_reason = failover_reason  # type: ignore[possibly-undefined]
            emit_telemetry(response, pipeline_stage)
            logger.info(
                "LLM request completed via failover",
                extra={
                    "provider": response.provider,
                    "model": response.model,
                    "latency_ms": response.latency_ms,
                    "pipeline_stage": pipeline_stage,
                    "failover": True,
                },
            )
            return response

        except (LLMProviderError, LLMInvalidResponseError) as secondary_exc:
            total_ms = int((time.monotonic() - t_start) * 1000)
            secondary_reason = (
                f"{type(secondary_exc).__name__}: {secondary_exc.message}"
                if hasattr(secondary_exc, "message")
                else str(secondary_exc)
            )
            emit_failure_telemetry(
                pipeline_stage=pipeline_stage,
                error_code="GATEWAY_EXHAUSTED",
                provider="all",
                model="all",
                latency_ms=total_ms,
            )
            logger.error(
                "LLM gateway exhausted — all providers failed",
                extra={
                    "pipeline_stage": pipeline_stage,
                    "total_latency_ms": total_ms,
                    "secondary_reason": secondary_reason,
                },
            )
            raise LLMGatewayExhaustedError(
                f"Primary ({self._primary.provider_name}) and "
                f"secondary ({self._secondary.provider_name}) providers both failed."
            ) from secondary_exc

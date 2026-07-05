"""
SWASTHYA AI CORE — LLM Usage Telemetry.

Tracks LLM usage metrics for cost monitoring and performance analysis.
Symptoms and PHI are NEVER included in telemetry records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from src.common.correlation import get_correlation_id
from src.infrastructure.llm.providers.base import LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class LLMTelemetryRecord:
    """Immutable telemetry snapshot for one LLM call."""

    correlation_id: str
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    estimated_cost_usd: float
    retry_count: int
    failover_triggered: bool
    failover_reason: str
    pipeline_stage: str
    success: bool
    error_code: str = ""


def emit_telemetry(response: LLMResponse, pipeline_stage: str) -> None:
    """
    Emit a structured telemetry log record for a completed LLM call.

    This is the single, canonical place where LLM usage metrics are recorded.
    All pipelines call this function after receiving an LLMResponse.
    """
    record = LLMTelemetryRecord(
        correlation_id=get_correlation_id(),
        provider=response.provider,
        model=response.model,
        prompt_version=response.prompt_version,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        total_tokens=response.input_tokens + response.output_tokens,
        latency_ms=response.latency_ms,
        estimated_cost_usd=response.estimated_cost_usd,
        retry_count=response.retry_count,
        failover_triggered=response.failover_triggered,
        failover_reason=response.failover_reason,
        pipeline_stage=pipeline_stage,
        success=True,
    )

    logger.info(
        "llm_telemetry",
        extra={
            "telemetry": {
                "correlation_id": record.correlation_id,
                "provider": record.provider,
                "model": record.model,
                "prompt_version": record.prompt_version,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "total_tokens": record.total_tokens,
                "latency_ms": record.latency_ms,
                "estimated_cost_usd": round(record.estimated_cost_usd, 6),
                "retry_count": record.retry_count,
                "failover_triggered": record.failover_triggered,
                "failover_reason": record.failover_reason,
                "pipeline_stage": record.pipeline_stage,
                "success": record.success,
            }
        },
    )


def emit_failure_telemetry(
    pipeline_stage: str,
    error_code: str,
    provider: str = "unknown",
    model: str = "unknown",
    latency_ms: int = 0,
) -> None:
    """Emit a telemetry record for a failed LLM call."""
    logger.error(
        "llm_telemetry_failure",
        extra={
            "telemetry": {
                "correlation_id": get_correlation_id(),
                "provider": provider,
                "model": model,
                "pipeline_stage": pipeline_stage,
                "success": False,
                "error_code": error_code,
                "latency_ms": latency_ms,
            }
        },
    )

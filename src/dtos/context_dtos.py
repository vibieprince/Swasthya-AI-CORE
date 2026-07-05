"""
SWASTHYA AI CORE — Context DTOs.

Data Transfer Objects for the POST /api/context/analyze endpoint.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.domain.context.models import PatientContext


class ContextAnalyzeRequest(BaseModel):
    """Input payload for context analysis."""

    message: str = Field(..., min_length=2, max_length=2000, description="Raw patient message")
    correlation_id: Optional[str] = Field(None, description="Optional client-provided correlation ID")


class ContextAnalyzeResponse(BaseModel):
    """Output payload representing the extracted and validated patient context."""

    context_id: str
    
    # Intelligence
    language_code: str
    detected_intent: str
    is_healthcare_query: bool
    is_greeting: bool
    
    # Validation state
    is_context_sufficient: bool
    needs_followup: bool
    followup_question: Optional[str] = None
    missing_fields: list[str] = Field(default_factory=list)
    
    # Full Context Object representation for downstream use
    context_data: PatientContext
    
    # Telemetry
    processing_latency_ms: int

    @classmethod
    def from_domain(cls, context: PatientContext) -> ContextAnalyzeResponse:
        """Convert a domain PatientContext into a Response DTO."""
        return cls(
            context_id=context.context_id,
            language_code=context.language.language_code,
            detected_intent=context.language.detected_intent.value,
            is_healthcare_query=context.language.is_healthcare_query,
            is_greeting=context.language.is_greeting,
            is_context_sufficient=context.validation.is_context_sufficient,
            needs_followup=context.validation.needs_followup,
            followup_question=context.validation.followup_question,
            missing_fields=context.validation.missing_fields,
            context_data=context,
            processing_latency_ms=context.processing_latency_ms,
        )

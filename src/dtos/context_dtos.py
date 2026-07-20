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
    context_id: Optional[str] = Field(
        None,
        description=(
            "Optional. Pass the context_id returned by a previous call to continue "
            "a multi-turn conversation. If omitted, a new conversation is started."
        ),
    )
    correlation_id: Optional[str] = Field(None, description="Optional client-provided trace/correlation ID")


class ContextAnalyzeResponse(BaseModel):
    """Output payload representing the extracted and validated patient context."""

    context_id: Optional[str]  # None for greetings (no session created yet)
    session_version: int
    
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

    # Session metadata — new fields; backward-compatible (clients may ignore)
    conversation_state: Optional[str] = None   # Current ConversationState value
    block_reason: Optional[str] = None         # Stable code, e.g. MANDATORY_PATIENT_LOCATION_REFUSED
    block_message: Optional[str] = None        # User-facing explanation of why conversation is blocked
    
    # Full Context Object representation for downstream use (Omitted if incomplete)
    context_data: Optional[PatientContext] = None
    
    # Telemetry
    processing_latency_ms: int

    @classmethod
    def from_domain(cls, context: PatientContext) -> ContextAnalyzeResponse:
        """Convert a domain PatientContext into a Response DTO."""
        is_sufficient = context.validation.is_context_sufficient
        is_greeting = context.language.is_greeting
        return cls(
            # Return None for greetings: no Redis session was created for this context_id
            # so the client should NOT store it or send it back.
            context_id=None if is_greeting else context.context_id,
            session_version=context.session_version,
            language_code=context.language.language_code,
            detected_intent=context.language.detected_intent.value,
            is_healthcare_query=context.language.is_healthcare_query,
            is_greeting=is_greeting,
            is_context_sufficient=is_sufficient,
            needs_followup=context.validation.needs_followup,
            followup_question=context.validation.followup_question,
            missing_fields=context.validation.missing_fields,
            conversation_state=context.validation.conversation_state,
            block_reason=context.validation.block_reason,
            block_message=context.validation.block_message,
            context_data=context if is_sufficient else None,
            processing_latency_ms=context.processing_latency_ms,
        )

    def model_dump(self, **kwargs):
        """Always exclude none values to minimize payload size for incomplete contexts."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

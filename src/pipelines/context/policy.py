"""
SWASTHYA AI CORE — Conversation Policy Engine.

Deterministically controls context gathering and clinical enrichment.
Designed to guarantee finite conversation lengths and prevent infinite loops.
"""

from __future__ import annotations

from typing import Optional

from src.common.logging import get_logger
from src.domain.context.enums import ConversationState
from src.domain.context.models import ClinicalData, ConversationSession, MissingField, PolicyDecision

logger = get_logger(__name__)


class ConversationPolicy:
    """
    Evaluates patient context and session history to determine the next action.
    """

    # Maximum number of times we will ask for the EXACT same field
    # before giving up and moving on, preventing infinite loops.
    _MAX_RETRIES_PER_FIELD = 1

    def evaluate(self, session: Optional[ConversationSession], clinical: ClinicalData) -> PolicyDecision:
        """
        Evaluate the current context to determine if we need more information.
        """
        # ── Emergency Bypass (highest priority) ───────────────────────────
        # Emergency patients skip ALL optional clinical questioning.
        # However, Discovery cannot locate a nearby hospital without any geographic
        # signal — so location remains the single exception we will ask for once.
        if clinical.is_emergency:
            has_location = (
                bool(clinical.patient_location.city)
                or bool(clinical.patient_location.raw_location)
            )
            if has_location:
                # Location known — proceed immediately. No more questions.
                return PolicyDecision(
                    is_context_sufficient=True,
                    needs_followup=False,
                    reason="Emergency with known location. Proceeding to Discovery immediately.",
                    next_state=ConversationState.CONTEXT_READY,
                )
            # Location unknown — ask ONE urgent question then stop, bypassing all
            # other optional checks. The anti-loop guard in _decide() still applies,
            # so this conversation still terminates deterministically.
            return self._decide(
                session=session,
                field_id="patient_location",
                display_name="the city or area where the patient needs emergency care",
                purpose="emergency hospital search",
                next_state=ConversationState.WAITING_FOR_LOCATION,
                is_mandatory=True,
            )

        has_symptoms = bool(clinical.symptoms)
        has_specialty = clinical.preferred_specialty is not None
        has_location = bool(clinical.patient_location.city) or bool(clinical.patient_location.raw_location)

        # ── Priority 1: Geographic Location (Mandatory) ──────────────────
        if not has_location:
            return self._decide(
                session=session,
                field_id="patient_location",
                display_name="your current city or area",
                purpose="hospital search",
                next_state=ConversationState.WAITING_FOR_LOCATION,
                is_mandatory=True,
            )

        # ── Priority 2: Symptoms or Specialty (Mandatory) ────────────────
        if not has_symptoms and not has_specialty:
            return self._decide(
                session=session,
                field_id="primary_symptoms",
                display_name="your main symptoms or the type of doctor you need",
                purpose="finding the right specialist",
                next_state=ConversationState.GATHERING_CLINICAL_INFO,
                is_mandatory=True,
            )

        # ── Context Complete ─────────────────────────────────────────────────
        return PolicyDecision(
            is_context_sufficient=True,
            needs_followup=False,
            reason="All mandatory fields satisfied.",
            next_state=ConversationState.CONTEXT_READY,
        )

    def _decide(
        self,
        session: Optional[ConversationSession],
        field_id: str,
        display_name: str,
        purpose: str,
        next_state: ConversationState,
        is_mandatory: bool,
    ) -> PolicyDecision:
        """
        Safely generates a follow-up decision, applying anti-loop protection.
        """
        # If no session exists yet (e.g. Pass 1 just finished), we can't loop yet.
        if not session:
            return PolicyDecision(
                is_context_sufficient=False,
                needs_followup=True,
                followup_field=MissingField(id=field_id, display_name=display_name, purpose=purpose),
                reason=f"Missing {is_mandatory and 'mandatory' or 'enrichment'} field: {field_id}",
                next_state=next_state,
            )

        # Anti-Loop Protection
        if session.last_followup_field == field_id:
            if session.last_followup_count >= self._MAX_RETRIES_PER_FIELD:
                logger.warning(
                    "Conversation loop prevented",
                    extra={"session_id": session.session_id, "field": field_id, "retries": session.last_followup_count}
                )
                if is_mandatory:
                    # We cannot proceed without location/symptoms, but we must prevent infinite loops.
                    # Instead of forging sufficiency, we explicitly BLOCK the conversation.
                    # The Context API remains the single source of truth for incompleteness.
                    block_reason_code = f"MANDATORY_{field_id.upper()}_REFUSED"
                    block_msg = (
                        f"Providing {display_name} is required to find nearby hospitals. "
                        "Please start a new conversation to try again."
                    )
                    return PolicyDecision(
                        is_context_sufficient=False,
                        needs_followup=False,
                        reason=f"Conversation BLOCKED. Max retries exceeded for mandatory field '{field_id}'.",
                        next_state=ConversationState.BLOCKED,
                        block_reason=block_reason_code,
                        block_message=block_msg,
                    )
                else:
                    # It's an enrichment field. User is ignoring it. Skip it.
                    return PolicyDecision(
                        is_context_sufficient=True,
                        needs_followup=False,
                        reason=f"Skipping enrichment field '{field_id}' due to max retries.",
                        next_state=ConversationState.CONTEXT_READY,
                    )

        return PolicyDecision(
            is_context_sufficient=False,
            needs_followup=True,
            followup_field=MissingField(id=field_id, display_name=display_name, purpose=purpose),
            reason=f"Missing {is_mandatory and 'mandatory' or 'enrichment'} field: {field_id}",
            next_state=next_state,
        )

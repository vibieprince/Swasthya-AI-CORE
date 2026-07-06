"""
SWASTHYA AI CORE — Context Pipeline Orchestrator.

Wires Pass 1 -> Pass 2 -> Pass 3 with short-circuit logic for greetings
and irrelevant messages.

Multi-turn Conversation Memory (Redis):
  Key   : swasthya:context:{session_id}
  TTL   : 30 minutes of inactivity (abandonment cleanup)
  ON COMPLETE : DO NOT delete. Increment version if clinical data changes.
                Post-discovery follow-up questions still belong to this session.
  ON EXPIRE   : Return ContextExpiredError (HTTP 410) to the client.

Conversation State Machine:
  Driven by ConversationState rather than stateless intent detection.
"""

from __future__ import annotations

import time
import uuid

from src.common.exceptions import ContextPipelineError, ContextExpiredError
from src.common.logging import get_logger
from src.domain.context.models import (
    ClinicalData,
    ContextValidation,
    LanguageIntelligence,
    PatientContext,
    ConversationSession,
)
from src.domain.context.enums import ConversationState, ClinicalIntent
from src.infrastructure.llm.gateway import LLMGateway
from src.pipelines.context.pass1_language_intent import Pass1LanguageIntentDetector
from src.pipelines.context.pass2_clinical import Pass2ClinicalExtractor
from src.pipelines.context.pass3_validation import Pass3Validator

logger = get_logger(__name__)


class ContextOrchestrator:
    """
    Orchestrates the three-pass context intelligence pipeline.

    Routing logic:
    - NEW_SESSION (Greeting)   -> Return greeting. Do not start Redis session.
    - NEW_SESSION (Irrelevant) -> Return fast response. Do not start Redis session.
    - NEW_SESSION (Healthcare) -> Start Redis session. Run Pass1 -> Pass2 (Full).
    - CONTINUATION             -> Load session. Skip Pass1. Run Pass2 (Delta).
                                  Python merge. Determine new state.
    """

    _CONTEXT_KEY_PREFIX = "swasthya:context:"
    _CONTEXT_TTL_SECONDS = 1800  # 30 minutes rolling inactivity window

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway
        self._pass1 = Pass1LanguageIntentDetector(gateway)
        self._pass2 = Pass2ClinicalExtractor(gateway)
        self._pass3 = Pass3Validator(gateway)

    async def run(self, message: str, context_id: str | None = None) -> PatientContext:
        """
        Execute the full context intelligence pipeline driven by state machine.
        """
        from src.infrastructure.redis.client import cache_get, cache_set

        t_pipeline_start = time.monotonic()
        now_ms = int(time.time() * 1000)

        # ── Conversation memory: load or create ──────────────────────────────
        session: ConversationSession | None = None
        is_continuation = False

        if context_id:
            key = f"{self._CONTEXT_KEY_PREFIX}{context_id}"
            raw = await cache_get(key)
            if raw is None:
                raise ContextExpiredError(context_id)
            try:
                session = ConversationSession.model_validate_json(raw)
                is_continuation = True
                logger.info(
                    "Continuing conversation from Redis",
                    extra={
                        "context_id": context_id,
                        "state": session.state.value,
                        "version": session.version,
                    },
                )
            except Exception as exc:
                logger.error(
                    "Failed to deserialise stored ConversationSession — raising expired error",
                    extra={"context_id": context_id, "error": str(exc)},
                )
                raise ContextExpiredError(context_id) from exc
        else:
            context_id = str(uuid.uuid4())

        # ── New Session Logic ────────────────────────────────────────────────
        if not is_continuation:
            # Pass 1: Language + Intent ONLY on new sessions
            language: LanguageIntelligence = await self._pass1.run(message)

            if language.is_greeting:
                greeting_response = self._generate_greeting(language.language_code)
                # DO NOT SAVE TO REDIS - wait for actual healthcare query
                return PatientContext(
                    context_id=context_id,
                    session_version=1,
                    language=language,
                    clinical=ClinicalData(),
                    validation=ContextValidation(
                        is_context_sufficient=False,
                        needs_followup=True,
                        followup_question=greeting_response,
                        context_confidence=1.0,
                        validation_notes="Greeting detected -- no clinical context yet.",
                    ),
                    raw_message=message,
                    processing_latency_ms=int((time.monotonic() - t_pipeline_start) * 1000),
                )

            if language.is_irrelevant:
                return PatientContext(
                    context_id=context_id,
                    session_version=1,
                    language=language,
                    clinical=ClinicalData(),
                    validation=ContextValidation(
                        is_context_sufficient=False,
                        needs_followup=False,
                        context_confidence=1.0,
                        validation_notes="Irrelevant query -- not a healthcare request.",
                    ),
                    raw_message=message,
                    processing_latency_ms=int((time.monotonic() - t_pipeline_start) * 1000),
                )

            # It's a healthcare query, run full extraction
            clinical = await self._pass2.run(
                message=message,
                language_code=language.language_code,
                intent=language.detected_intent,
            )
            
            # Start a new session wrapper
            session = ConversationSession(
                session_id=context_id,
                state=ConversationState.GATHERING_CLINICAL_INFO,
                version=1,
                patient_context=PatientContext(
                    context_id=context_id,
                    session_version=1,
                    language=language,
                    clinical=clinical,
                    validation=ContextValidation(), # Will be replaced below
                    raw_message=message,
                ),
                created_at_ms=now_ms,
                updated_at_ms=now_ms,
            )

        # ── Continuation Logic (State Machine) ───────────────────────────────
        else:
            assert session is not None
            # Skip Pass1. Reuse language and intent.
            language = session.patient_context.language
            
            # If we are in POST_DISCOVERY_QA, we might not want to re-extract clinical data.
            # But the user said: "Example: Hospital recommended -> Actually pain shifted to abdomen -> Now recommendation changes. Still Accept Context Updates -> Increment Context Version."
            # So we STILL run Pass 2 Delta Extraction to capture any new clinical entities!

            # Pass 2: Delta Extraction & Python Merge
            clinical = await self._pass2.run_merge(
                message=message,
                language_code=language.language_code,
                intent=language.detected_intent,
                existing_clinical=session.patient_context.clinical,
            )

        # ── Deterministic Sufficiency Check (Python) ─────────────────────────
        missing = []
        has_symptoms_or_specialty = bool(clinical.symptoms) or (clinical.preferred_specialty is not None)
        if not has_symptoms_or_specialty:
            missing.append("symptoms_or_specialty")

        has_location = bool(clinical.patient_location.city) or bool(clinical.patient_location.raw_location)
        if not has_location:
            missing.append("location")

        is_sufficient = len(missing) == 0

        # ── Determine if data changed (for versioning) ───────────────────────
        data_changed = False
        if is_continuation:
            # Simple check: did the json representation of clinical data change?
            old_json = session.patient_context.clinical.model_dump_json(exclude_none=True)
            new_json = clinical.model_dump_json(exclude_none=True)
            if old_json != new_json:
                data_changed = True

        # ── Pass 3: Validation + Follow-up ───────────────────────────────────
        if is_sufficient:
            validation = ContextValidation(
                is_context_sufficient=True,
                missing_fields=[],
                needs_followup=False,
                followup_question=None,
                followup_question_english=None,
                context_confidence=0.95,
                validation_notes="Context is sufficient. Ready for Discovery.",
            )
            new_state = ConversationState.CONTEXT_READY
        else:
            # Need follow-up. LLM generates natural language question.
            validation = await self._pass3.run(
                clinical=clinical,
                language_code=language.language_code,
                intent=language.detected_intent.value,
                missing_fields=missing,
            )
            # Determine precise waiting state
            if "location" in missing and not has_symptoms_or_specialty:
                 new_state = ConversationState.GATHERING_CLINICAL_INFO
            elif "location" in missing:
                 new_state = ConversationState.WAITING_FOR_LOCATION
            else:
                 new_state = ConversationState.GATHERING_CLINICAL_INFO


        total_latency_ms = int((time.monotonic() - t_pipeline_start) * 1000)

        # Increment version if data changed, so Discovery knows to re-run
        if is_continuation and data_changed:
            session.version += 1

        patient_context = PatientContext(
            context_id=context_id,
            session_version=session.version,
            language=language,
            clinical=clinical,
            validation=validation,
            raw_message=message,
            processing_latency_ms=total_latency_ms,
        )

        # ── Update Session ───────────────────────────────────────────────────
        session.patient_context = patient_context
        session.state = new_state
        session.updated_at_ms = now_ms
        if validation.followup_question:
            session.last_question = validation.followup_question

        # Save to Redis
        context_redis_key = f"{self._CONTEXT_KEY_PREFIX}{context_id}"
        from src.infrastructure.redis.client import cache_set
        await cache_set(
            context_redis_key,
            session.model_dump_json(),
            self._CONTEXT_TTL_SECONDS,
        )

        logger.info(
            "Context pipeline completed",
            extra={
                "context_id": context_id,
                "is_continuation": is_continuation,
                "version": session.version,
                "state": new_state.value,
                "is_sufficient": is_sufficient,
                "missing_fields": missing,
                "total_latency_ms": total_latency_ms,
            },
        )

        return patient_context

    def _generate_greeting(self, language_code: str) -> str:
        """Deterministically generate a warm, language-appropriate greeting message."""
        greetings = {
            "en": "Hello! I'm MedPath AI. Please describe your symptoms or what kind of hospital you are looking for so I can help.",
            "hi": "namaste! main MedPath AI hun. kripaya apne lakshanon ka varnan karen taki main aapko sabse achhe aspatal dhundhne mein madad kar sakun.",
            "ta": "vanakkam! nan MedPath AI. cirantha maruttuvamanaigalai theda ungal arikiurugalai vivarikavum.",
            "te": "namaskaram! nenu MedPath AI ni. saraina asupathri kanugonataniki dayachesi mee lakshanaalanu vivarinchandi.",
            "bn": "namaskar! ami MedPath AI. sera haspathal khuje peta anugrahapurvak apnar lakshanguli barnana karun.",
            "mr": "namaskar! mi MedPath AI aahe. sarvottam rugnalay shodhanyas kripaya tumachi lakshane sanga.",
            "gu": "namaste! hun MedPath AI chun. yogya hospital shodhava mate krupa karine tamara lakshano varnavao.",
            "kn": "namaskara! nanu MedPath AI. uttama aspatreyannu hudukalu dayavittu nimma rogalakshanagalannu vivarisiri.",
            "ml": "namaskaram! njan MedPath AI aan. mikachha asupathri kandettaan ningalude rogalakshanangal vishad-eekarikkuka.",
        }
        return greetings.get(language_code.lower(), greetings["en"])

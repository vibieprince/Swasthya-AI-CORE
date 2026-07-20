"""
SWASTHYA AI CORE — Context Pipeline Combined Pass.

Executes Language Detection, Intent Classification, and Clinical Extraction
in a single LLM invocation for new sessions. Replaces the sequential Pass 1 -> Pass 2 flow
to reduce conversational latency by one full LLM round trip (~2.5s to 3s).
"""

from __future__ import annotations

import time

from src.common.exceptions import ContextPipelineError
from src.common.logging import get_logger
from src.common.prompts.context_prompts import (
    COMBINED_PASS_SYSTEM,
    COMBINED_PASS_USER_TEMPLATE,
    PROMPT_VERSION,
)
from src.domain.context.enums import (
    BudgetPreference,
    ClinicalIntent,
    HospitalTypePreference,
    InsuranceScheme,
    MedicalSpecialty,
    PregnancyStatus,
    UrgencyLevel,
)
from src.domain.context.models import (
    BudgetContext,
    ClinicalData,
    InsuranceContext,
    LanguageIntelligence,
    PatientLocation,
)
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest
from src.pipelines.context.pass2_clinical import _safe_enum

logger = get_logger(__name__)


class CombinedInitialAnalysisPass:
    """
    Context Pipeline Combined Pass (Pass 1 + Pass 2).

    Executes on NEW sessions to extract everything simultaneously.
    If the message is just a greeting or irrelevant, clinical fields are left empty.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def run(self, message: str) -> tuple[LanguageIntelligence, ClinicalData]:
        """
        Execute combined analysis.

        Args:
            message: Raw patient message.

        Returns:
            Tuple of (LanguageIntelligence, ClinicalData)

        Raises:
            ContextPipelineError: On LLM failure or parse error.
        """
        t_start = time.monotonic()

        valid_specialties = [e.value for e in MedicalSpecialty]
        valid_urgencies = [e.value for e in UrgencyLevel]

        request = LLMRequest(
            system_prompt=COMBINED_PASS_SYSTEM,
            user_prompt=COMBINED_PASS_USER_TEMPLATE.format(
                message=message,
                valid_specialties=", ".join(valid_specialties),
                valid_urgencies=", ".join(valid_urgencies),
            ),
            temperature=0.05,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(request, pipeline_stage="context_combined_pass")
        except Exception as exc:
            raise ContextPipelineError(
                stage="combined_initial_analysis",
                message=f"LLM gateway failed in Combined Pass: {exc}",
            ) from exc

        p = response.parsed
        latency_ms = int((time.monotonic() - t_start) * 1000)

        # ── Parse Language Intelligence ─────────────────────────────────────────
        try:
            language = LanguageIntelligence(
                language_code=p.get("language_code", "en"),
                language_name=p.get("language_name", "English"),
                is_greeting=bool(p.get("is_greeting", False)),
                is_healthcare_query=bool(p.get("is_healthcare_query", True)),
                is_irrelevant=bool(p.get("is_irrelevant", False)),
                detected_intent=ClinicalIntent(
                    p.get("detected_intent", ClinicalIntent.FIND_HOSPITAL.value)
                ),
                confidence=float(p.get("confidence", 0.8)),
                reasoning=p.get("reasoning", ""),
            )
        except (KeyError, ValueError) as exc:
            raise ContextPipelineError(
                stage="combined_initial_analysis",
                message=f"Failed to parse LanguageIntelligence: {exc}",
            ) from exc

        # ── Parse Clinical Data ────────────────────────────────────────────────
        try:
            loc_raw = p.get("patient_location", {}) or {}
            budget_raw = p.get("budget_inr", {}) or {}
            insurance_raw = p.get("insurance", {}) or {}

            raw_specialty = p.get("preferred_specialty")
            specialty: MedicalSpecialty | None = None
            if raw_specialty:
                specialty = _safe_enum(MedicalSpecialty, raw_specialty, None)

            raw_scheme = insurance_raw.get("scheme")
            scheme = _safe_enum(InsuranceScheme, raw_scheme, None) if raw_scheme else None

            clinical = ClinicalData(
                symptoms=p.get("symptoms", []) or [],
                symptom_duration_days=p.get("symptom_duration_days"),
                pain_level=p.get("pain_level"),
                is_emergency=bool(p.get("is_emergency", False)),
                pregnancy_status=_safe_enum(
                    PregnancyStatus,
                    p.get("pregnancy_status"),
                    PregnancyStatus.UNKNOWN,
                ),
                medical_history=p.get("medical_history", []) or [],
                current_medications=p.get("current_medications", []) or [],
                allergies=p.get("allergies", []) or [],
                age_years=p.get("age_years"),
                gender=p.get("gender"),
                patient_location=PatientLocation(
                    city=loc_raw.get("city"),
                    state=loc_raw.get("state"),
                    pincode=loc_raw.get("pincode"),
                    raw_location=loc_raw.get("raw_location"),
                ),
                budget=BudgetContext(
                    min_inr=budget_raw.get("min"),
                    max_inr=budget_raw.get("max"),
                    preference=_safe_enum(
                        BudgetPreference,
                        budget_raw.get("preference"),
                        BudgetPreference.ANY,
                    ),
                ),
                insurance=InsuranceContext(
                    has_insurance=insurance_raw.get("has_insurance"),
                    provider=insurance_raw.get("provider"),
                    scheme=scheme,
                ),
                preferred_specialty=specialty,
                urgency_level=_safe_enum(
                    UrgencyLevel,
                    p.get("urgency_level"),
                    UrgencyLevel.ROUTINE,
                ),
                preferred_hospital_type=_safe_enum(
                    HospitalTypePreference,
                    p.get("preferred_hospital_type"),
                    HospitalTypePreference.BOTH,
                ),
                preferred_gender_doctor=p.get("preferred_gender_doctor"),
            )
        except Exception as exc:
            raise ContextPipelineError(
                stage="combined_initial_analysis",
                message=f"Failed to parse ClinicalData: {exc}",
            ) from exc

        logger.info(
            "Combined Initial Analysis completed",
            extra={
                "language": language.language_code,
                "intent": language.detected_intent.value,
                "is_greeting": language.is_greeting,
                "symptom_count": len(clinical.symptoms),
                "is_emergency": clinical.is_emergency,
                "latency_ms": latency_ms,
            },
        )
        return language, clinical

"""
SWASTHYA AI CORE — Context Pipeline Pass 2.

Full clinical extraction: symptoms, location, budget, insurance,
medical history, urgency, specialty mapping, and demographics.
"""

from __future__ import annotations

import time
from typing import Any

from src.common.exceptions import ContextPipelineError
from src.common.logging import get_logger
from src.common.prompts.context_prompts import (
    PASS2_MERGE_SYSTEM,
    PASS2_MERGE_USER_TEMPLATE,
    PASS2_SYSTEM,
    PASS2_USER_TEMPLATE,
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
    PatientLocation,
)
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.llm.providers.base import LLMRequest

logger = get_logger(__name__)


def _safe_enum(enum_class: type, value: Any, default: Any) -> Any:
    """
    Safely coerce a value to an enum, returning default on failure.

    Case-insensitive matching: Gemini may return 'Orthopedics' when the
    enum defines 'orthopedics'. We normalise both sides before comparing.
    """
    if value is None:
        return default
    if not isinstance(value, str):
        try:
            return enum_class(value)
        except (ValueError, KeyError):
            return default

    value_stripped = value.strip()

    # Direct match first (fast path)
    try:
        return enum_class(value_stripped)
    except (ValueError, KeyError):
        pass

    # Case-insensitive fallback
    value_lower = value_stripped.lower()
    for member in enum_class:
        if member.value.lower() == value_lower:
            return member

    # Partial match: handle 'Orthopaedic' vs 'orthopedics' etc.
    for member in enum_class:
        if value_lower.startswith(member.value.lower()[:6]) or member.value.lower().startswith(value_lower[:6]):
            return member

    return default


class Pass2ClinicalExtractor:
    """
    Context Pipeline Pass 2.

    Extracts all structured clinical signals from the patient message.
    Operates on the language and intent context from Pass 1.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def run(
        self,
        message: str,
        language_code: str,
        intent: ClinicalIntent,
    ) -> ClinicalData:
        """
        Execute Pass 2 clinical extraction.

        Args:
            message: Raw patient message.
            language_code: Detected language from Pass 1.
            intent: Detected clinical intent from Pass 1.

        Returns:
            Fully populated ClinicalData domain object.

        Raises:
            ContextPipelineError: On LLM failure or parse error.
        """
        t_start = time.monotonic()

        # Build valid specialty list so Gemini knows exactly what values to output
        valid_specialties = [e.value for e in MedicalSpecialty]
        valid_urgencies = [e.value for e in UrgencyLevel]

        request = LLMRequest(
            system_prompt=PASS2_SYSTEM,
            user_prompt=PASS2_USER_TEMPLATE.format(
                language_code=language_code,
                message=message,
                intent=intent.value,
                valid_specialties=", ".join(valid_specialties),
                valid_urgencies=", ".join(valid_urgencies),
            ),
            temperature=0.05,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(request, pipeline_stage="context_pass2")
        except Exception as exc:
            raise ContextPipelineError(
                stage="pass2_clinical_extraction",
                message=f"LLM gateway failed in Pass 2: {exc}",
            ) from exc

        p = response.parsed
        latency_ms = int((time.monotonic() - t_start) * 1000)

        try:
            loc_raw = p.get("patient_location", {}) or {}
            budget_raw = p.get("budget_inr", {}) or {}
            insurance_raw = p.get("insurance", {}) or {}

            # Specialty mapping
            raw_specialty = p.get("preferred_specialty")
            specialty: MedicalSpecialty | None = None
            if raw_specialty:
                specialty = _safe_enum(MedicalSpecialty, raw_specialty, None)

            # Insurance scheme
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
                stage="pass2_clinical_extraction",
                message=f"Failed to build ClinicalData from LLM response: {exc}",
            ) from exc

        logger.info(
            "Pass 2 completed",
            extra={
                "symptom_count": len(clinical.symptoms),
                "has_location": clinical.patient_location.city is not None,
                "urgency": clinical.urgency_level.value,
                "is_emergency": clinical.is_emergency,
                "latency_ms": latency_ms,
            },
        )
        return clinical

    async def run_merge(
        self,
        message: str,
        language_code: str,
        intent: ClinicalIntent,
        existing_clinical: ClinicalData,
    ) -> ClinicalData:
        """
        Execute Pass 2 in MERGE mode for multi-turn conversations.

        Sends the existing ClinicalData snapshot alongside the new message.
        The LLM is instructed to only fill in null/empty fields, preserving
        all confirmed values from previous turns.

        Args:
            message: Latest raw patient message.
            language_code: Detected language from Pass 1.
            intent: Detected clinical intent from Pass 1.
            existing_clinical: ClinicalData stored from a previous turn.

        Returns:
            Updated ClinicalData with previously missing fields filled in.
        """
        t_start = time.monotonic()

        valid_specialties = [e.value for e in MedicalSpecialty]
        valid_urgencies = [e.value for e in UrgencyLevel]

        request = LLMRequest(
            system_prompt=PASS2_MERGE_SYSTEM,
            user_prompt=PASS2_MERGE_USER_TEMPLATE.format(
                language_code=language_code,
                message=message,
                intent=intent.value,
                valid_specialties=", ".join(valid_specialties),
                valid_urgencies=", ".join(valid_urgencies),
            ),
            temperature=0.05,
            prompt_version=PROMPT_VERSION,
        )

        try:
            response = await self._gateway.complete(request, pipeline_stage="context_pass2_merge")
        except Exception as exc:
            raise ContextPipelineError(
                stage="pass2_clinical_merge",
                message=f"LLM gateway failed in Pass 2 merge: {exc}",
            ) from exc

        p = response.parsed
        latency_ms = int((time.monotonic() - t_start) * 1000)

        try:
            loc_raw = p.get("patient_location", {}) or {}
            budget_raw = p.get("budget_inr", {}) or {}
            insurance_raw = p.get("insurance", {}) or {}
            ex = existing_clinical  # shorthand

            raw_specialty = p.get("preferred_specialty")
            specialty: MedicalSpecialty | None = None
            if raw_specialty:
                specialty = _safe_enum(MedicalSpecialty, raw_specialty, None)
            # Fall back to existing if LLM returned nothing new
            if specialty is None:
                specialty = ex.preferred_specialty

            raw_scheme = insurance_raw.get("scheme")
            scheme = _safe_enum(InsuranceScheme, raw_scheme, None) if raw_scheme else None
            if scheme is None:
                scheme = ex.insurance.scheme

            # ── Python-level non-destructive merge ──────────────────────────────
            # Rule: for each field, prefer the LLM's new value only when it is
            # non-null/non-empty.  If the LLM returned null/empty, keep the value
            # that was already confirmed in a previous turn.
            def _pick_list(new: list, old: list) -> list:
                return new if new else old

            def _pick_val(new, old):
                return new if new is not None else old

            # Location: build from LLM output, fall back field-by-field
            new_loc = PatientLocation(
                city=_pick_val(loc_raw.get("city"), ex.patient_location.city),
                state=_pick_val(loc_raw.get("state"), ex.patient_location.state),
                pincode=_pick_val(loc_raw.get("pincode"), ex.patient_location.pincode),
                raw_location=_pick_val(loc_raw.get("raw_location"), ex.patient_location.raw_location),
            )

            # Budget: prefer new only when non-default
            new_budget_pref = _safe_enum(BudgetPreference, budget_raw.get("preference"), None)
            merged = ClinicalData(
                symptoms=_pick_list(p.get("symptoms", []) or [], ex.symptoms),
                symptom_duration_days=_pick_val(p.get("symptom_duration_days"), ex.symptom_duration_days),
                pain_level=_pick_val(p.get("pain_level"), ex.pain_level),
                # is_emergency: once True, always True; otherwise trust new value
                is_emergency=ex.is_emergency or bool(p.get("is_emergency", False)),
                pregnancy_status=_safe_enum(
                    PregnancyStatus,
                    p.get("pregnancy_status"),
                    ex.pregnancy_status,
                ),
                medical_history=_pick_list(p.get("medical_history", []) or [], ex.medical_history),
                current_medications=_pick_list(p.get("current_medications", []) or [], ex.current_medications),
                allergies=_pick_list(p.get("allergies", []) or [], ex.allergies),
                age_years=_pick_val(p.get("age_years"), ex.age_years),
                gender=_pick_val(p.get("gender"), ex.gender),
                patient_location=new_loc,
                budget=BudgetContext(
                    min_inr=_pick_val(budget_raw.get("min"), ex.budget.min_inr),
                    max_inr=_pick_val(budget_raw.get("max"), ex.budget.max_inr),
                    preference=new_budget_pref if new_budget_pref else ex.budget.preference,
                ),
                insurance=InsuranceContext(
                    has_insurance=_pick_val(insurance_raw.get("has_insurance"), ex.insurance.has_insurance),
                    provider=_pick_val(insurance_raw.get("provider"), ex.insurance.provider),
                    scheme=scheme,
                ),
                preferred_specialty=specialty,
                urgency_level=_safe_enum(
                    UrgencyLevel, p.get("urgency_level"), ex.urgency_level
                ),
                preferred_hospital_type=_safe_enum(
                    HospitalTypePreference,
                    p.get("preferred_hospital_type"),
                    ex.preferred_hospital_type,
                ),
                preferred_gender_doctor=_pick_val(p.get("preferred_gender_doctor"), ex.preferred_gender_doctor),
            )
        except Exception as exc:
            raise ContextPipelineError(
                stage="pass2_clinical_merge",
                message=f"Failed to build merged ClinicalData: {exc}",
            ) from exc

        logger.info(
            "Pass 2 merge completed",
            extra={
                "symptom_count": len(merged.symptoms),
                "has_location": merged.patient_location.city is not None or merged.patient_location.raw_location is not None,
                "urgency": merged.urgency_level.value,
                "latency_ms": latency_ms,
            },
        )
        return merged


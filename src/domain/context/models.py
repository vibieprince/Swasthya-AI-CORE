"""
SWASTHYA AI CORE — Context Domain Models.

Pure domain objects representing the patient context intelligence output.
These models carry no persistence logic and are fully stateless.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.domain.context.enums import (
    BudgetPreference,
    ClinicalIntent,
    DetectedLanguage,
    HospitalTypePreference,
    InsuranceScheme,
    MedicalSpecialty,
    PregnancyStatus,
    UrgencyLevel,
)


class PatientLocation(BaseModel):
    """Geographic context provided by the patient."""

    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    raw_location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class BudgetContext(BaseModel):
    """Patient's financial context for hospital discovery."""

    min_inr: Optional[int] = None
    max_inr: Optional[int] = None
    preference: BudgetPreference = BudgetPreference.ANY


class InsuranceContext(BaseModel):
    """Patient's insurance and government scheme context."""

    has_insurance: Optional[bool] = None
    provider: Optional[str] = None
    scheme: Optional[InsuranceScheme] = None


class ClinicalData(BaseModel):
    """
    Extracted clinical signals from the patient message.

    PRIVACY: This model may be held in memory but MUST NEVER be:
    - Logged with symptoms visible
    - Persisted to any data store
    - Included in error payloads
    """

    symptoms: list[str] = Field(default_factory=list)
    symptom_duration_days: Optional[int] = None
    pain_level: Optional[int] = Field(default=None, ge=1, le=10)
    is_emergency: bool = False
    pregnancy_status: PregnancyStatus = PregnancyStatus.UNKNOWN
    medical_history: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    age_years: Optional[int] = None
    gender: Optional[str] = None
    patient_location: PatientLocation = Field(default_factory=PatientLocation)
    budget: BudgetContext = Field(default_factory=BudgetContext)
    insurance: InsuranceContext = Field(default_factory=InsuranceContext)
    preferred_specialty: Optional[MedicalSpecialty] = None
    urgency_level: UrgencyLevel = UrgencyLevel.ROUTINE
    preferred_hospital_type: HospitalTypePreference = HospitalTypePreference.BOTH
    preferred_gender_doctor: Optional[str] = None


class LanguageIntelligence(BaseModel):
    """Output of Pass 1 language and intent detection."""

    language_code: str = "en"
    language_name: str = "English"
    is_greeting: bool = False
    is_healthcare_query: bool = True
    is_irrelevant: bool = False
    detected_intent: ClinicalIntent = ClinicalIntent.FIND_HOSPITAL
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str = ""


class ContextValidation(BaseModel):
    """Output of Pass 3 validation and follow-up generation."""

    is_context_sufficient: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    needs_followup: bool = False
    followup_question: Optional[str] = None
    followup_question_english: Optional[str] = None
    context_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_notes: str = ""


class PatientContext(BaseModel):
    """
    Complete, validated patient context produced by the context pipeline.

    This is the primary output of /api/context/analyze and the primary
    input to /api/discovery/search.
    """

    context_id: str
    language: LanguageIntelligence
    clinical: ClinicalData
    validation: ContextValidation
    raw_message: str
    processing_latency_ms: int = 0

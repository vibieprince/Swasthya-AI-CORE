"""
SWASTHYA AI CORE — Context Domain Enums.

All enumerations used in the context intelligence pipeline.
"""

from __future__ import annotations

from enum import Enum


class DetectedLanguage(str, Enum):
    """ISO 639-1 language codes supported by the platform."""

    ENGLISH = "en"
    HINDI = "hi"
    TAMIL = "ta"
    TELUGU = "te"
    BENGALI = "bn"
    MARATHI = "mr"
    GUJARATI = "gu"
    KANNADA = "kn"
    MALAYALAM = "ml"
    PUNJABI = "pa"
    ODIA = "or"
    UNKNOWN = "unknown"


class ClinicalIntent(str, Enum):
    """High-level intent categories for patient queries."""

    FIND_HOSPITAL = "FIND_HOSPITAL"
    FIND_DOCTOR = "FIND_DOCTOR"
    SYMPTOM_INQUIRY = "SYMPTOM_INQUIRY"
    EMERGENCY = "EMERGENCY"
    COST_INQUIRY = "COST_INQUIRY"
    INSURANCE_INQUIRY = "INSURANCE_INQUIRY"
    GENERAL_HEALTH = "GENERAL_HEALTH"
    GREETING = "GREETING"
    IRRELEVANT = "IRRELEVANT"


class UrgencyLevel(str, Enum):
    """Clinical urgency classification."""

    IMMEDIATE = "IMMEDIATE"   # Life-threatening, go now
    URGENT = "URGENT"         # Needs attention within hours
    ROUTINE = "ROUTINE"       # Standard appointment
    ELECTIVE = "ELECTIVE"     # Non-urgent, planned care


class PregnancyStatus(str, Enum):
    """Patient pregnancy status."""

    PREGNANT = "pregnant"
    NOT_PREGNANT = "not_pregnant"
    UNKNOWN = "unknown"


class BudgetPreference(str, Enum):
    """Patient budget tier."""

    ECONOMY = "economy"
    STANDARD = "standard"
    PREMIUM = "premium"
    ANY = "any"


class InsuranceScheme(str, Enum):
    """Major insurance and government schemes in India."""

    CGHS = "CGHS"
    PMJAY = "PMJAY"
    ESI = "ESI"
    PRIVATE = "private"
    NONE = "none"


class HospitalTypePreference(str, Enum):
    """Patient preference for hospital governance type."""

    GOVERNMENT = "government"
    PRIVATE = "private"
    BOTH = "both"


class MedicalSpecialty(str, Enum):
    """Primary medical specialties for search routing."""

    CARDIOLOGY = "Cardiology"
    NEUROLOGY = "Neurology"
    ORTHOPEDICS = "Orthopedics"
    ONCOLOGY = "Oncology"
    GYNECOLOGY = "Gynecology"
    PEDIATRICS = "Pediatrics"
    DERMATOLOGY = "Dermatology"
    GASTROENTEROLOGY = "Gastroenterology"
    NEPHROLOGY = "Nephrology"
    UROLOGY = "Urology"
    OPHTHALMOLOGY = "Ophthalmology"
    ENT = "ENT"
    PSYCHIATRY = "Psychiatry"
    PULMONOLOGY = "Pulmonology"
    ENDOCRINOLOGY = "Endocrinology"
    RHEUMATOLOGY = "Rheumatology"
    GENERAL_SURGERY = "General Surgery"
    GENERAL_MEDICINE = "General Medicine"
    EMERGENCY_MEDICINE = "Emergency Medicine"
    RADIOLOGY = "Radiology"
    PATHOLOGY = "Pathology"
    ANESTHESIOLOGY = "Anesthesiology"
    PHYSIOTHERAPY = "Physiotherapy"
    DENTISTRY = "Dentistry"
    FERTILITY = "Fertility"
    TRANSPLANT = "Transplant"
    UNKNOWN = "Unknown"


class ConversationState(str, Enum):
    """Explicit state machine for the context conversation lifecycle."""

    NEW_SESSION = "NEW_SESSION"
    WAITING_FOR_HEALTH_QUERY = "WAITING_FOR_HEALTH_QUERY"
    GATHERING_CLINICAL_INFO = "GATHERING_CLINICAL_INFO"
    WAITING_FOR_LOCATION = "WAITING_FOR_LOCATION"
    CONTEXT_READY = "CONTEXT_READY"
    POST_DISCOVERY_QA = "POST_DISCOVERY_QA"
    SESSION_EXPIRED = "SESSION_EXPIRED"

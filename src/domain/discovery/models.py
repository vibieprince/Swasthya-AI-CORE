"""
SWASTHYA AI CORE — Discovery Domain Models.

Pure domain objects for the hospital discovery pipeline.
No persistence. No business state.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.domain.context.enums import BudgetPreference, HospitalTypePreference, MedicalSpecialty, UrgencyLevel


class SearchLocation(BaseModel):
    """Geographic context for a discovery request."""

    city: str
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw_text: Optional[str] = None


class SearchStrategy(BaseModel):
    """Generated search strategy for a discovery request."""

    primary_search_queries: list[str] = Field(default_factory=list)
    nabh_search_terms: list[str] = Field(default_factory=list)
    specialty_keywords: list[str] = Field(default_factory=list)
    location_variants: list[str] = Field(default_factory=list)
    search_radius_km: int = 25
    priority_filters: dict[str, bool] = Field(default_factory=dict)
    search_depth: str = "standard"


class HospitalCoordinates(BaseModel):
    """Precise geographic coordinates for a hospital."""

    latitude: float
    longitude: float
    google_maps_place_id: Optional[str] = None
    google_maps_url: Optional[str] = None
    formatted_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    coordinate_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class HospitalCandidate(BaseModel):
    """
    A raw hospital candidate discovered from search sources.

    This is an intermediate model before normalization and ranking.
    """

    candidate_id: str
    hospital_name: str
    raw_address: Optional[str] = None
    coordinates: Optional[HospitalCoordinates] = None
    contact_number: Optional[str] = None
    website: Optional[str] = None
    source: str = "unknown"  # tavily | maps | nabh | scrape
    source_url: Optional[str] = None
    hospital_type: Optional[str] = None
    accreditations: list[str] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)
    has_emergency: Optional[bool] = None
    has_icu: Optional[bool] = None
    overall_rating: Optional[float] = None
    review_count: Optional[int] = None
    estimated_cost_min_inr: Optional[int] = None
    estimated_cost_max_inr: Optional[int] = None
    key_strengths: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)
    clinical_notes: Optional[str] = None
    data_quality_score: float = Field(default=0.5, ge=0.0, le=1.0)
    raw_scrape_data: Optional[str] = None


class DiscoveryRequest(BaseModel):
    """Input for a hospital discovery task."""

    task_id: str
    context_id: str
    specialty: MedicalSpecialty
    location: SearchLocation
    urgency: UrgencyLevel = UrgencyLevel.ROUTINE
    budget_preference: BudgetPreference = BudgetPreference.ANY
    hospital_type_preference: HospitalTypePreference = HospitalTypePreference.BOTH
    is_emergency: bool = False
    max_results: int = Field(default=4, ge=2, le=4)
    language_code: str = "en"
    correlation_id: str = ""

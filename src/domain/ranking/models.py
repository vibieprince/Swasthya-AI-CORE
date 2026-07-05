"""
SWASTHYA AI CORE — Ranking Domain Models.

Final ranked recommendation output models.
These represent the terminal output of the entire discovery + ranking pipeline.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CostRange(BaseModel):
    """Estimated cost range for a hospital in INR."""

    min_inr: Optional[int] = None
    max_inr: Optional[int] = None
    currency: str = "INR"


class RankingScores(BaseModel):
    """Multi-criteria scoring components for a hospital."""

    clinical_suitability_score: float = Field(ge=0.0, le=1.0)
    affordability_score: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=1.0)
    accessibility_score: float = Field(ge=0.0, le=1.0)
    trust_score: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)


class RankedHospital(BaseModel):
    """
    A fully ranked and explained hospital recommendation.

    This is the final output object returned to MedPath.
    All coordinates and navigation data are included so MedPath
    never needs to perform a secondary location lookup.
    """

    rank: int = Field(ge=1, le=4)
    hospital_name: str
    hospital_type: str

    # ── Location (mandatory when resolved) ────────────────────────────────────
    formatted_address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_km: Optional[float] = None
    estimated_travel_time_minutes: Optional[int] = None
    google_maps_place_id: Optional[str] = None
    google_maps_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None

    # ── Contact ────────────────────────────────────────────────────────────────
    contact_number: Optional[str] = None
    website: Optional[str] = None

    # ── Quality Signals ────────────────────────────────────────────────────────
    accreditations: list[str] = Field(default_factory=list)
    overall_rating: Optional[float] = None
    review_count: Optional[int] = None
    has_emergency: bool = False
    has_icu: bool = False
    estimated_cost_range: CostRange = Field(default_factory=CostRange)

    # ── Scoring ────────────────────────────────────────────────────────────────
    scores: RankingScores

    # ── Explainability ─────────────────────────────────────────────────────────
    recommendation_summary: str
    recommendation_summary_english: str
    why_this_rank: str
    top_reasons: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    confidence_explanation: str = ""


class RecommendationBundle(BaseModel):
    """
    The terminal output of the discovery + ranking + explanation pipeline.

    Contains 2–4 ranked hospitals with full explainability.
    """

    task_id: str
    context_id: str
    specialty: str
    location_searched: str
    recommendations: list[RankedHospital] = Field(default_factory=list)
    total_candidates_evaluated: int = 0
    search_depth_used: str = "standard"
    pipeline_latency_ms: int = 0
    sources_used: list[str] = Field(default_factory=list)

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

    min_inr: Optional[int] = Field(default=None)
    max_inr: Optional[int] = Field(default=None)
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

    # ── Location ─────────────────────────────────────────────────────────────
    formatted_address: Optional[str] = Field(default=None)
    latitude: Optional[float] = Field(default=None, exclude=True)
    longitude: Optional[float] = Field(default=None, exclude=True)
    distance_km: Optional[float] = Field(default=None)
    estimated_travel_time_minutes: Optional[int] = Field(default=None)
    google_maps_place_id: Optional[str] = Field(default=None, exclude=True)
    google_maps_url: Optional[str] = Field(default=None, exclude=True)

    # ── Contact ────────────────────────────────────────────────────────────────
    contact_number: Optional[str] = Field(default=None)
    website: Optional[str] = Field(default=None)

    # ── Quality Signals ────────────────────────────────────────────────────────
    accreditations: list[str] = Field(default_factory=list)
    overall_rating: Optional[float] = Field(default=None)
    review_count: Optional[int] = Field(default=None)
    has_emergency: bool = False
    has_icu: bool = False
    estimated_cost_range: Optional[CostRange] = Field(default=None)

    # ── Scoring ────────────────────────────────────────────────────────────────
    overall_score: float = Field(ge=0.0, le=1.0)
    scores: RankingScores = Field(exclude=True)

    # ── Explainability ─────────────────────────────────────────────────────────
    summary: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


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
    
    # Internal logging metadata (excluded from public response)
    total_candidates_evaluated: int = Field(default=0, exclude=True)
    search_depth_used: str = Field(default="standard", exclude=True)
    pipeline_latency_ms: int = Field(default=0, exclude=True)
    sources_used: list[str] = Field(default_factory=list, exclude=True)

    def model_dump(self, **kwargs) -> dict:
        """Always exclude unset and none values from response."""
        kwargs.setdefault("exclude_none", True)
        kwargs.setdefault("exclude_unset", True)
        kwargs.setdefault("exclude_defaults", False)
        # Drop empty arrays for clean payload
        dumped = super().model_dump(**kwargs)
        for rec in dumped.get("recommendations", []):
            if "accreditations" in rec and not rec["accreditations"]:
                del rec["accreditations"]
            if "pros" in rec and not rec["pros"]:
                del rec["pros"]
            if "cons" in rec and not rec["cons"]:
                del rec["cons"]
        return dumped

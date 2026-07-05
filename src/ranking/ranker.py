"""
SWASTHYA AI CORE — Hospital Ranker.

Takes scored candidates and produces a final sorted RankedHospital list.
"""

from __future__ import annotations

from typing import Tuple

from src.common.logging import get_logger
from src.domain.discovery.models import DiscoveryRequest, HospitalCandidate
from src.domain.ranking.models import CostRange, RankedHospital, RankingScores
from src.ranking.scorer import HospitalScorer

logger = get_logger(__name__)


class HospitalRanker:
    """
    Applies multi-criteria scoring and sorts candidates to produce final recommendations.
    """

    def __init__(self) -> None:
        self._scorer = HospitalScorer()

    def rank(
        self,
        candidates: list[HospitalCandidate],
        request: DiscoveryRequest,
    ) -> list[RankedHospital]:
        """Rank candidates and return the top N matches."""
        
        if not candidates:
            return []

        # 1. Score all candidates
        scored_candidates: list[Tuple[HospitalCandidate, RankingScores, float]] = []
        for candidate in candidates:
            scores = self._scorer.score(candidate, request)
            
            # Overall score formulation
            # Weightings adapt based on urgency
            if request.is_emergency:
                overall_score = (
                    scores.accessibility_score * 0.5 + 
                    scores.clinical_suitability_score * 0.4 +
                    scores.quality_score * 0.1
                )
            else:
                overall_score = (
                    scores.clinical_suitability_score * 0.35 +
                    scores.quality_score * 0.3 +
                    scores.affordability_score * 0.2 +
                    scores.accessibility_score * 0.15
                )
                
            # Penalize low confidence heavily
            overall_score *= scores.confidence_score
            
            scored_candidates.append((candidate, scores, overall_score))

        # 2. Sort by overall score descending
        scored_candidates.sort(key=lambda x: x[2], reverse=True)

        # 3. Take Top N (requested max_results, typically 2-4)
        top_candidates = scored_candidates[:request.max_results]

        # 4. Map to RankedHospital DTOs
        ranked_hospitals: list[RankedHospital] = []
        for rank_idx, (candidate, scores, _) in enumerate(top_candidates):
            
            # Safely compute distance and travel time if coordinates exist
            dist_km = None
            travel_mins = None
            if candidate.coordinates and request.location.latitude and request.location.longitude:
                dist_km = self._scorer._haversine(
                    request.location.latitude, request.location.longitude,
                    candidate.coordinates.latitude, candidate.coordinates.longitude
                )
                # Rough heuristic: 25 km/h avg city speed -> ~2.4 mins per km
                travel_mins = int(dist_km * 2.4)
                
            ranked = RankedHospital(
                rank=rank_idx + 1,
                hospital_name=candidate.hospital_name,
                hospital_type=candidate.hospital_type or "private",
                formatted_address=candidate.coordinates.formatted_address if candidate.coordinates else candidate.raw_address,
                latitude=candidate.coordinates.latitude if candidate.coordinates else None,
                longitude=candidate.coordinates.longitude if candidate.coordinates else None,
                distance_km=dist_km,
                estimated_travel_time_minutes=travel_mins,
                google_maps_place_id=candidate.coordinates.google_maps_place_id if candidate.coordinates else None,
                google_maps_url=candidate.coordinates.google_maps_url if candidate.coordinates else None,
                city=candidate.coordinates.city if candidate.coordinates else None,
                state=candidate.coordinates.state if candidate.coordinates else None,
                pincode=candidate.coordinates.pincode if candidate.coordinates else None,
                contact_number=candidate.contact_number,
                website=candidate.website,
                accreditations=candidate.accreditations,
                overall_rating=candidate.overall_rating,
                review_count=candidate.review_count,
                has_emergency=bool(candidate.has_emergency),
                has_icu=bool(candidate.has_icu),
                estimated_cost_range=CostRange(
                    min_inr=candidate.estimated_cost_min_inr,
                    max_inr=candidate.estimated_cost_max_inr,
                ),
                scores=scores,
                # Explainability fields will be populated by the Explainer step
                recommendation_summary="",
                recommendation_summary_english="",
                why_this_rank="",
                top_reasons=candidate.key_strengths[:3],
                cautions=candidate.known_limitations[:1],
                confidence_explanation="",
            )
            ranked_hospitals.append(ranked)

        logger.info(
            "Ranking completed", 
            extra={"task_id": request.task_id, "returned_count": len(ranked_hospitals)}
        )
        return ranked_hospitals

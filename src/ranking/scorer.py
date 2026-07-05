"""
SWASTHYA AI CORE — Hospital Scorer.

Calculates multi-criteria ranking scores for hospital candidates.
"""

from __future__ import annotations

import math

from src.common.logging import get_logger
from src.domain.discovery.models import DiscoveryRequest, HospitalCandidate
from src.domain.ranking.models import RankingScores

logger = get_logger(__name__)


class HospitalScorer:
    """
    Computes objective scores for each candidate across 5 dimensions:
    - Clinical Suitability
    - Affordability
    - Quality (Ratings, Accreditations)
    - Accessibility (Distance)
    - Trust (Composite of quality, data completeness)
    """

    def score(
        self,
        candidate: HospitalCandidate,
        request: DiscoveryRequest,
    ) -> RankingScores:
        """Score a single candidate against the patient's request context."""
        
        clinical_score = self._score_clinical(candidate, request)
        affordability_score = self._score_affordability(candidate, request)
        quality_score = self._score_quality(candidate)
        accessibility_score = self._score_accessibility(candidate, request)
        
        # Trust score is heavily weighted by accreditations and data quality
        trust_score = (quality_score * 0.7) + (candidate.data_quality_score * 0.3)
        
        # Confidence score indicates how sure the system is about this recommendation
        # (Heavily penalizes lack of coordinates or completely missing price data)
        confidence_score = 1.0
        if not candidate.coordinates:
            confidence_score *= 0.5
        if not candidate.estimated_cost_max_inr:
            confidence_score *= 0.8
        confidence_score *= candidate.data_quality_score
        
        return RankingScores(
            clinical_suitability_score=clinical_score,
            affordability_score=affordability_score,
            quality_score=quality_score,
            accessibility_score=accessibility_score,
            trust_score=trust_score,
            confidence_score=confidence_score,
        )

    def _score_clinical(self, candidate: HospitalCandidate, request: DiscoveryRequest) -> float:
        score = 0.5 # Base score
        
        # Check emergency match
        if request.is_emergency and candidate.has_emergency:
            score += 0.3
        elif request.is_emergency and not candidate.has_emergency:
            score -= 0.4
            
        # Check specialty match
        if request.specialty.value.lower() in [s.lower() for s in candidate.specialties]:
            score += 0.2
            
        return max(0.0, min(1.0, score))

    def _score_affordability(self, candidate: HospitalCandidate, request: DiscoveryRequest) -> float:
        pref = request.budget_preference.value.lower()
        if pref == "any":
            return 1.0
            
        # If we don't have cost data, we apply a neutral score
        if not candidate.estimated_cost_max_inr:
            return 0.5
            
        # Rough heuristic tiers (mock logic for scoring)
        # Economy < 10000, Standard 10k-50k, Premium > 50k
        cost = candidate.estimated_cost_max_inr
        
        if pref == "economy":
            if cost <= 15000: return 1.0
            if cost <= 30000: return 0.5
            return 0.2
        elif pref == "standard":
            if 10000 <= cost <= 60000: return 1.0
            return 0.6
        elif pref == "premium":
            if cost >= 40000: return 1.0
            return 0.7
            
        return 0.5

    def _score_quality(self, candidate: HospitalCandidate) -> float:
        score = 0.3 # Base
        
        if "NABH" in candidate.accreditations:
            score += 0.3
        if "JCI" in candidate.accreditations:
            score += 0.2
            
        if candidate.overall_rating:
            # Map 1.0-5.0 rating to 0.0-0.2 score boost
            rating_boost = (candidate.overall_rating / 5.0) * 0.2
            score += rating_boost
            
        return max(0.0, min(1.0, score))

    def _score_accessibility(self, candidate: HospitalCandidate, request: DiscoveryRequest) -> float:
        if not candidate.coordinates or not request.location.latitude or not request.location.longitude:
            return 0.5 # Unknown distance
            
        # Calculate distance
        dist_km = self._haversine(
            request.location.latitude,
            request.location.longitude,
            candidate.coordinates.latitude,
            candidate.coordinates.longitude,
        )
        
        # Closer is better, decays exponentially
        # 0km = 1.0, 10km ~ 0.6, 25km ~ 0.36
        score = math.exp(-dist_km / 20.0)
        return max(0.0, min(1.0, score))
        
    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

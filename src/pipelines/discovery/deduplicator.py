"""
SWASTHYA AI CORE — Hospital Candidate Deduplicator.

Deduplicates hospital candidates from multiple search sources using
fuzzy string matching on hospital names and coordinate proximity.
"""

from __future__ import annotations

import math
from typing import Optional

from rapidfuzz import fuzz

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate

logger = get_logger(__name__)

_NAME_SIMILARITY_THRESHOLD = 85.0    # 0–100
_COORDINATE_PROXIMITY_METERS = 200   # metres


class HospitalDeduplicator:
    """
    Deduplicates a mixed list of HospitalCandidates.

    Merging strategy:
    1. Fuzzy match on normalised hospital name (RapidFuzz token_sort_ratio)
    2. Coordinate proximity check (< 200m = same hospital)

    When duplicates are found:
    - The candidate with the highest data_quality_score is kept as base
    - Fields from duplicates are merged in (filling gaps)
    """

    def deduplicate(self, candidates: list[HospitalCandidate]) -> list[HospitalCandidate]:
        """
        Deduplicate a list of hospital candidates.

        Args:
            candidates: Raw mixed-source candidates.

        Returns:
            Deduplicated list with data merged across duplicates.
        """
        if len(candidates) <= 1:
            return candidates

        merged: list[HospitalCandidate] = []

        for candidate in candidates:
            match_idx = self._find_duplicate(candidate, merged)
            if match_idx is None:
                merged.append(candidate)
            else:
                merged[match_idx] = self._merge(merged[match_idx], candidate)

        logger.info(
            "Deduplication completed",
            extra={
                "input_count": len(candidates),
                "output_count": len(merged),
                "removed_count": len(candidates) - len(merged),
            },
        )
        return merged

    def _find_duplicate(
        self,
        candidate: HospitalCandidate,
        existing: list[HospitalCandidate],
    ) -> Optional[int]:
        """Return the index of a matching existing candidate, or None."""
        for idx, existing_c in enumerate(existing):
            if self._is_duplicate(candidate, existing_c):
                return idx
        return None

    def _is_duplicate(self, a: HospitalCandidate, b: HospitalCandidate) -> bool:
        """Return True if two candidates represent the same hospital."""
        # Coordinate check (most reliable)
        if a.coordinates and b.coordinates:
            dist = self._distance_meters(a.coordinates, b.coordinates)
            if dist < _COORDINATE_PROXIMITY_METERS:
                return True

        # Google Maps Place ID (authoritative)
        if (
            a.coordinates
            and b.coordinates
            and a.coordinates.google_maps_place_id
            and b.coordinates.google_maps_place_id
            and a.coordinates.google_maps_place_id == b.coordinates.google_maps_place_id
        ):
            return True

        # Fuzzy name match
        similarity = fuzz.token_sort_ratio(
            self._normalise_name(a.hospital_name),
            self._normalise_name(b.hospital_name),
        )
        return similarity >= _NAME_SIMILARITY_THRESHOLD

    @staticmethod
    def _normalise_name(name: str) -> str:
        """Normalise hospital name for comparison."""
        name = name.lower().strip()
        for suffix in [
            "hospital", "hospitals", "clinic", "clinics", "healthcare",
            "medical centre", "medical center", "nursing home", "pvt", "ltd",
            "private limited", "private", "limited",
        ]:
            name = name.replace(suffix, "").strip()
        return name

    @staticmethod
    def _distance_meters(
        a: "HospitalCandidate.coordinates",  # type: ignore[name-defined]
        b: "HospitalCandidate.coordinates",  # type: ignore[name-defined]
    ) -> float:
        """Approximate haversine distance in metres between two coordinate sets."""
        R = 6_371_000  # Earth radius in metres
        lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
        dlat = math.radians(b.latitude - a.latitude)
        dlon = math.radians(b.longitude - a.longitude)
        a_ = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * R * math.atan2(math.sqrt(a_), math.sqrt(1 - a_))

    @staticmethod
    def _merge(primary: HospitalCandidate, duplicate: HospitalCandidate) -> HospitalCandidate:
        """Merge duplicate into primary, filling gaps from duplicate."""
        # Keep primary as base; fill None fields from duplicate
        if not primary.coordinates and duplicate.coordinates:
            primary.coordinates = duplicate.coordinates
        if not primary.contact_number and duplicate.contact_number:
            primary.contact_number = duplicate.contact_number
        if not primary.website and duplicate.website:
            primary.website = duplicate.website
        if not primary.raw_address and duplicate.raw_address:
            primary.raw_address = duplicate.raw_address
        if not primary.overall_rating and duplicate.overall_rating:
            primary.overall_rating = duplicate.overall_rating
        if not primary.review_count and duplicate.review_count:
            primary.review_count = duplicate.review_count

        # Merge accreditations
        existing_accreditations = set(primary.accreditations)
        for acc in duplicate.accreditations:
            if acc not in existing_accreditations:
                primary.accreditations.append(acc)

        # Upgrade data quality score
        primary.data_quality_score = max(
            primary.data_quality_score,
            duplicate.data_quality_score,
        )

        # Append scrape data if primary has none
        if not primary.raw_scrape_data and duplicate.raw_scrape_data:
            primary.raw_scrape_data = duplicate.raw_scrape_data

        return primary

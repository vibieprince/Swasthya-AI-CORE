"""
SWASTHYA AI CORE — Review Extractor.

Extracts review sentiment and key review points from raw scraped data.
Currently uses heuristics and keyword matching to keep latency low before Gemini summarization.
"""

from __future__ import annotations

import re

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate

logger = get_logger(__name__)

_POSITIVE_KEYWORDS = {"excellent", "good", "great", "best", "caring", "clean", "professional", "helpful", "friendly"}
_NEGATIVE_KEYWORDS = {"bad", "worst", "terrible", "dirty", "rude", "expensive", "wait", "delayed", "unprofessional"}


class ReviewExtractor:
    """
    Extracts high-level review themes and signals from raw text.
    These themes are appended to known_limitations and key_strengths.
    """

    def extract_all(self, candidates: list[HospitalCandidate]) -> list[HospitalCandidate]:
        """Extract reviews for all candidates."""
        for candidate in candidates:
            self._extract(candidate)
        return candidates

    def _extract(self, candidate: HospitalCandidate) -> None:
        """Extract review signals from a single candidate's raw data."""
        text = candidate.raw_scrape_data
        if not text:
            return

        text_lower = text.lower()
        
        # Simple heuristic extraction
        positive_matches = [kw for kw in _POSITIVE_KEYWORDS if kw in text_lower]
        negative_matches = [kw for kw in _NEGATIVE_KEYWORDS if kw in text_lower]

        if len(positive_matches) > 2 and "patient satisfaction" not in candidate.key_strengths:
            candidate.key_strengths.append("High patient satisfaction indicators")
            
        if "expensive" in negative_matches and "Potentially high cost" not in candidate.known_limitations:
            candidate.known_limitations.append("Potentially high cost")
            
        if "wait" in negative_matches and "Long wait times mentioned" not in candidate.known_limitations:
            candidate.known_limitations.append("Long wait times mentioned")

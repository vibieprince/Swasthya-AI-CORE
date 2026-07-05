"""
SWASTHYA AI CORE — Facility Extractor.

Extracts structured facility indicators (ICU, Emergency, Bed count)
from raw scraped text using regex and heuristics.
"""

from __future__ import annotations

import re

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate

logger = get_logger(__name__)


class FacilityExtractor:
    """
    Extracts objective facility signals (Emergency, ICU, Beds) 
    from raw text before sending to LLM.
    """

    def extract_all(self, candidates: list[HospitalCandidate]) -> list[HospitalCandidate]:
        for candidate in candidates:
            self._extract(candidate)
        return candidates

    def _extract(self, candidate: HospitalCandidate) -> None:
        text = candidate.raw_scrape_data
        if not text:
            return

        text_lower = text.lower()

        # Emergency Detection
        if candidate.has_emergency is None:
            if re.search(r"\b(24/7|24x7|24 hours|emergency|casualty|trauma)\b", text_lower):
                candidate.has_emergency = True

        # ICU Detection
        if candidate.has_icu is None:
            if re.search(r"\b(icu|intensive care|nicu|picu|ccu)\b", text_lower):
                candidate.has_icu = True

        # Accreditations
        if "NABH" not in candidate.accreditations and re.search(r"\bnabh\b", text_lower):
            candidate.accreditations.append("NABH")
        
        if "JCI" not in candidate.accreditations and re.search(r"\bjci\b", text_lower):
            candidate.accreditations.append("JCI")
            
        if "NABL" not in candidate.accreditations and re.search(r"\bnabl\b", text_lower):
            candidate.accreditations.append("NABL")

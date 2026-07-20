"""
SWASTHYA AI CORE — Hospital Quality Gate Validator.

Rejects invalid candidates (e.g., SEO articles, generic searches) before they enter the ranking pipeline.
Ensures only real healthcare facilities are returned to the user.
"""

from __future__ import annotations

import re
from typing import List

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate

logger = get_logger(__name__)


class HospitalValidator:
    """
    Validates HospitalCandidate objects and removes non-hospital entities.
    """

    def validate_all(self, candidates: List[HospitalCandidate]) -> List[HospitalCandidate]:
        """Run all candidates through the quality gate."""
        valid_candidates: List[HospitalCandidate] = []
        for c in candidates:
            if self._is_valid(c):
                valid_candidates.append(c)
            else:
                logger.debug(
                    "Hospital candidate rejected by Quality Gate",
                    extra={"rejected_name": c.hospital_name, "source": c.source},
                )
        return valid_candidates

    def _is_valid(self, candidate: HospitalCandidate) -> bool:
        """Evaluate a single candidate."""
        name = candidate.hospital_name
        if not name:
            return False

        name_lower = name.lower()

        # 1. Reject by name patterns (SEO spam, questions, lists)
        rejection_patterns = [
            r"\b(top|best|vs|versus|difference)\b",
            r"\b(how|why|what|when|where|does|can)\b",
            r"\b(10|20|5|list of|directory)\b",
            r"\b(review|reviews|complaint|complaints)\b",
            r"(\?|!)",
        ]
        for pattern in rejection_patterns:
            if re.search(pattern, name_lower):
                return False

        # 2. Length constraints
        if len(name) > 60 or len(name) < 4:
            return False

        # 3. Confidence threshold
        # If the candidate comes from a weak source (like tavily or scrape) AND has no coordinates,
        # it is highly suspicious. Maps and NABH are authoritative.
        if candidate.source not in ["maps", "nabh"]:
            if not candidate.coordinates:
                # Require a strong hospital indicator in the name if it lacks coordinates and authoritative source
                strong_indicators = ["hospital", "clinic", "centre", "center", "institute", "aiims", "apollo", "fortis", "max"]
                if not any(kw in name_lower for kw in strong_indicators):
                    return False

        # 4. Data Quality minimum threshold
        if candidate.data_quality_score < 0.2:
            return False

        return True

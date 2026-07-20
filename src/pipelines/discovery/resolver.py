"""
SWASTHYA AI CORE — Hospital Entity Resolver.

Resolves departmental pages and SEO titles into canonical hospital entities.
Examples:
- "Cardiology at Fortis Hospital" -> "Fortis Hospital"
- "Leading Cardiologists and Heart Hospital in Greater Noida" -> "Heart Hospital"
"""

from __future__ import annotations

import re

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate

logger = get_logger(__name__)


class HospitalEntityResolver:
    """
    Transforms messy page titles and departmental names into canonical hospital entities.
    """

    def resolve_all(self, candidates: list[HospitalCandidate], city: str) -> list[HospitalCandidate]:
        """Resolve all candidates in-place."""
        for c in candidates:
            c.hospital_name = self.resolve_name(c.hospital_name, city)
        return candidates

    def resolve_name(self, name: str, city: str) -> str:
        """
        Extract the core hospital entity name from a messy string.
        """
        original_name = name
        name_lower = name.lower()

        # 1. Remove departmental prefixes (e.g., "Cardiology at ", "Department of Neurology - ")
        # If the string contains " at ", the hospital name is usually AFTER "at"
        if " at " in name_lower:
            name = re.split(r"(?i)\s+at\s+", name, maxsplit=1)[-1]
            
        # If the string starts with "Department of", remove it and anything before "-" or ","
        if name_lower.startswith("department of"):
            parts = re.split(r"(?i)\s*(?:-|\||,)\s*", name, maxsplit=1)
            if len(parts) > 1:
                name = parts[1]
                
        # If the string contains " in ", the hospital name is usually BEFORE "in"
        if " in " in name_lower:
            name = re.split(r"(?i)\s+in\s+", name, maxsplit=1)[0]

        # 2. Remove SEO padding like "Leading Cardiologists and "
        seo_prefixes = [
            r"^leading\s+.*?\s+and\s+",
            r"^top\s+.*?\s+at\s+",
            r"^best\s+.*?\s+in\s+",
            r"^find\s+.*?\s+at\s+",
        ]
        for pattern in seo_prefixes:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)

        # 3. Clean up the remainder (similar to normalizer)
        name = re.sub(r"\(.*?\)", "", name)
        name = re.sub(r"(?i)\b(pvt|ltd|private|limited|inc|llp)\b\.?", "", name)
        name = name.split(" - ")[0].split(" | ")[0].split(",")[0]
        
        # 4. Append city if not present and the name is very generic
        # e.g., "Heart Hospital" -> "Heart Hospital, Noida"
        name = " ".join(name.split()).strip()
        
        if not name:
            return original_name
            
        # Ensure it looks like a real entity
        if len(name) < 4:
            return original_name

        return name

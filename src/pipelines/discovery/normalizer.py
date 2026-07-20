"""
SWASTHYA AI CORE — Hospital Data Normalizer.

Normalises HospitalCandidate objects after deduplication.
Attempts to resolve missing coordinates via Google Maps.
Standardises address formats and contact numbers.
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate

logger = get_logger(__name__)

_INDIA_PHONE_PATTERN = re.compile(r"(\+91[\-\s]?)?[6-9]\d{9}")


class HospitalNormalizer:
    """
    Normalises and enriches HospitalCandidate data.

    Responsibilities:
    - Coordinate resolution (via Maps API) for candidates missing GPS
    - Phone number standardisation
    - Address formatting
    """

    async def normalize_all(
        self,
        candidates: list[HospitalCandidate],
        city: str,
    ) -> list[HospitalCandidate]:
        """
        Normalise a list of candidates, enriching coordinates where missing.

        Args:
            candidates: Deduplicated candidate list.
            city: Patient city for coordinate resolution fallback.

        Returns:
            Normalised candidate list.
        """
        semaphore = asyncio.Semaphore(4)

        async def _normalize_one(c: HospitalCandidate) -> HospitalCandidate:
            async with semaphore:
                return await self._normalize(c, city)

        normalised = await asyncio.gather(*[_normalize_one(c) for c in candidates])
        return list(normalised)

    async def _normalize(self, candidate: HospitalCandidate, city: str) -> HospitalCandidate:
        """Normalise a single HospitalCandidate."""
        # Clean up hospital name (Canonical Resolution)
        candidate.hospital_name = self._normalize_name(candidate.hospital_name)

        # Attempt coordinate resolution if missing
        if not candidate.coordinates or candidate.coordinates.latitude is None:
            from src.pipelines.discovery.maps_search import resolve_coordinates
            try:
                resolved = await resolve_coordinates(
                    hospital_name=candidate.hospital_name,
                    city=city,
                    existing_coords=candidate.coordinates,
                )
                if resolved:
                    candidate.coordinates = resolved
            except Exception as exc:
                logger.debug(
                    "Coordinate resolution failed",
                    extra={"hospital": candidate.hospital_name, "error": str(exc)[:100]},
                )

        # Normalise contact number
        if candidate.contact_number:
            candidate.contact_number = self._normalise_phone(candidate.contact_number)

        # Enrich city/state from coordinates if available
        if candidate.coordinates and candidate.coordinates.formatted_address:
            addr = candidate.coordinates.formatted_address
            parts = [p.strip() for p in addr.split(",")]
            if len(parts) >= 2:
                candidate.coordinates.city = parts[-3] if len(parts) >= 3 else None
                candidate.coordinates.state = parts[-2] if len(parts) >= 2 else None
                candidate.coordinates.pincode = self._extract_pincode(addr)

        return candidate

    @staticmethod
    def _normalise_phone(phone: str) -> str:
        """Standardise Indian phone numbers to +91 format."""
        digits = re.sub(r"[^\d+]", "", phone)
        if digits.startswith("+91") and len(digits) == 13:
            return digits
        if digits.startswith("91") and len(digits) == 12:
            return "+" + digits
        if len(digits) == 10 and digits[0] in "6789":
            return "+91" + digits
        return phone  # Return as-is if format unrecognised

    @staticmethod
    def _extract_pincode(address: str) -> Optional[str]:
        """Extract 6-digit Indian PIN code from an address string."""
        match = re.search(r"\b[1-9]\d{5}\b", address)
        return match.group(0) if match else None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        Produce a canonical hospital name by removing SEO spam and structural suffixes.
        """
        # Remove anything in parentheses (e.g. " (Best Hospital in Delhi)")
        name = re.sub(r"\(.*?\)", "", name)
        
        # Remove common corporate suffixes
        name = re.sub(r"(?i)\b(pvt|ltd|private|limited|inc|llp)\b\.?", "", name)
        
        # Remove common SEO trailing dashes
        name = name.split(" - ")[0].split(" | ")[0]
        
        return " ".join(name.split()).strip()

"""
SWASTHYA AI CORE — NABH Accreditation Search.

Scrapes the NABH (National Accreditation Board for Hospitals) directory
to discover accredited hospitals by location and specialty.

Uses BeautifulSoup4 with lxml for parsing.
"""

from __future__ import annotations

import uuid
from typing import Any

from bs4 import BeautifulSoup

from src.common.logging import get_logger
from src.domain.discovery.models import HospitalCandidate
from src.infrastructure.http.client import get_http_client

logger = get_logger(__name__)

_NABH_BASE_URL = "https://nabh.co/SearchHospitalsPublic.aspx"


class NABHSearcher:
    """
    Discovers NABH-accredited hospitals via web scraping.

    NABH accreditation is a strong positive quality signal for Indian hospitals.
    Results from this source are marked with NABH accreditation automatically.
    """

    async def search(self, city: str, specialty: str, task_id: str) -> list[HospitalCandidate]:
        """
        Search for NABH-accredited hospitals in a city.

        Returns:
            List of HospitalCandidate with NABH accreditation pre-populated.
        """
        client = get_http_client()
        candidates: list[HospitalCandidate] = []

        try:
            # NABH has a public search endpoint we query via GET params
            response = await client.get(
                _NABH_BASE_URL,
                params={"city": city, "category": "Hospital"},
                timeout=20.0,
            )
            if response.status_code != 200:
                logger.warning(
                    "NABH search returned non-200",
                    extra={"status": response.status_code, "task_id": task_id},
                )
                return []

            soup = BeautifulSoup(response.text, "lxml")
            candidates = self._parse_nabh_results(soup, task_id)

        except Exception as exc:
            logger.warning(
                "NABH search failed",
                extra={"error": str(exc), "task_id": task_id},
            )
            return []

        logger.info(
            "NABH search completed",
            extra={"task_id": task_id, "candidate_count": len(candidates), "city": city},
        )
        return candidates

    def _parse_nabh_results(
        self,
        soup: BeautifulSoup,
        task_id: str,
    ) -> list[HospitalCandidate]:
        """Parse NABH HTML response into HospitalCandidate objects."""
        candidates: list[HospitalCandidate] = []

        # NABH renders results in a GridView table or div list
        # We look for common patterns
        rows = soup.find_all("tr", class_=lambda c: c and "grid" in c.lower())
        if not rows:
            # Fallback: try any table row with hospital-like content
            rows = soup.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            name = cells[0].get_text(strip=True)
            if not name or len(name) < 3:
                continue

            address_text = cells[1].get_text(strip=True) if len(cells) > 1 else None

            candidates.append(
                HospitalCandidate(
                    candidate_id=str(uuid.uuid4()),
                    hospital_name=name,
                    raw_address=address_text,
                    source="nabh",
                    accreditations=["NABH"],
                    data_quality_score=0.7,
                )
            )

        return candidates

"""
SWASTHYA AI CORE — Google Maps Places Search.

Resolves hospital candidates using the Google Maps Places API (New).
Provides precise coordinates, formatted addresses, place IDs, and contact info.

This is the authoritative source for geographic data.
No hospital is returned without at least an attempt at coordinate resolution.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from typing import Any, Optional

from src.common.exceptions import MapsSearchError
from src.common.logging import get_logger
from src.config.settings import get_settings
from src.domain.discovery.models import (
    DiscoveryRequest,
    HospitalCandidate,
    HospitalCoordinates,
    SearchStrategy,
)
from src.infrastructure.http.client import get_http_client

logger = get_logger(__name__)

_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.userRatingCount,"
    "places.nationalPhoneNumber,places.websiteUri,"
    "places.regularOpeningHours,places.types"
)


class GoogleMapsSearcher:
    """
    Discovers and resolves hospitals using the Google Maps Places API.

    Performs:
    1. Text search for hospitals by specialty + location
    2. Coordinate extraction with Google Maps Place ID
    3. Distance calculation from patient location (if coords provided)
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def search(
        self,
        strategy: SearchStrategy,
        request: DiscoveryRequest,
    ) -> list[HospitalCandidate]:
        """
        Execute Google Maps hospital search.

        Returns:
            List of HospitalCandidate with precise coordinates.
        """
        loc = request.location
        queries = [
            f"{request.specialty.value} hospital in {loc.city}",
            f"best {request.specialty.value} hospital {loc.city} {loc.state or ''}".strip(),
        ]

        semaphore = asyncio.Semaphore(2)

        async def _query(q: str) -> list[HospitalCandidate]:
            async with semaphore:
                return await self._text_search(q, request)

        results = await asyncio.gather(*[_query(q) for q in queries], return_exceptions=True)

        candidates: list[HospitalCandidate] = []
        seen_place_ids: set[str] = set()

        for result in results:
            if isinstance(result, Exception):
                logger.warning("Maps query failed", extra={"error": str(result)})
                continue
            for c in result:
                pid = c.coordinates.google_maps_place_id if c.coordinates else None
                if pid and pid in seen_place_ids:
                    continue
                if pid:
                    seen_place_ids.add(pid)
                candidates.append(c)

        logger.info(
            "Google Maps search completed",
            extra={"task_id": request.task_id, "candidate_count": len(candidates)},
        )
        return candidates

    async def _text_search(
        self,
        query: str,
        request: DiscoveryRequest,
    ) -> list[HospitalCandidate]:
        """Execute a single Places Text Search API call."""
        client = get_http_client()
        payload: dict[str, Any] = {
            "textQuery": query,
            "languageCode": "en",
            "maxResultCount": 10,
        }

        # Add location bias if patient coords are available
        if request.location.latitude and request.location.longitude:
            payload["locationBias"] = {
                "circle": {
                    "center": {
                        "latitude": request.location.latitude,
                        "longitude": request.location.longitude,
                    },
                    "radius": float(50000),  # 50km
                }
            }

        try:
            response = await client.post(
                _PLACES_TEXT_SEARCH_URL,
                json=payload,
                headers={
                    "X-Goog-Api-Key": self._settings.google_maps_api_key,
                    "X-Goog-FieldMask": _FIELD_MASK,
                },
                timeout=15.0,
            )
            if response.status_code != 200:
                raise MapsSearchError(
                    f"Maps API HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            body = response.json()
        except MapsSearchError:
            raise
        except Exception as exc:
            raise MapsSearchError(f"Maps API request failed: {exc}") from exc

        candidates: list[HospitalCandidate] = []
        for place in body.get("places", []):
            candidate = self._place_to_candidate(place, request)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _place_to_candidate(
        self,
        place: dict[str, Any],
        request: DiscoveryRequest,
    ) -> Optional[HospitalCandidate]:
        """Convert a Google Places API result to a HospitalCandidate."""
        name_data = place.get("displayName", {})
        name = name_data.get("text", "").strip()
        if not name:
            return None

        place_id = place.get("id", "")
        location = place.get("location", {})
        lat = location.get("latitude")
        lng = location.get("longitude")

        coords: Optional[HospitalCoordinates] = None
        if lat is not None and lng is not None:
            coords = HospitalCoordinates(
                latitude=float(lat),
                longitude=float(lng),
                google_maps_place_id=place_id or None,
                google_maps_url=(
                    f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                    if place_id
                    else None
                ),
                formatted_address=place.get("formattedAddress"),
                coordinate_confidence=1.0,
            )

        # Calculate distance from patient if both coords available
        distance_km: Optional[float] = None
        if coords and request.location.latitude and request.location.longitude:
            distance_km = self._haversine(
                request.location.latitude,
                request.location.longitude,
                coords.latitude,
                coords.longitude,
            )

        return HospitalCandidate(
            candidate_id=str(uuid.uuid4()),
            hospital_name=name,
            raw_address=place.get("formattedAddress"),
            coordinates=coords,
            contact_number=place.get("nationalPhoneNumber"),
            website=place.get("websiteUri"),
            source="maps",
            overall_rating=place.get("rating"),
            review_count=place.get("userRatingCount"),
            data_quality_score=0.85,
        )

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance in km between two geographic coordinates."""
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def resolve_coordinates(
    hospital_name: str,
    city: str,
    existing_coords: Optional[HospitalCoordinates],
) -> Optional[HospitalCoordinates]:
    """
    Attempt to resolve or improve coordinates for a hospital.

    Used during normalization to enrich candidates that lack GPS data.
    """
    if existing_coords and existing_coords.latitude and existing_coords.longitude:
        return existing_coords  # Already resolved

    settings = get_settings()
    client = get_http_client()
    payload = {"textQuery": f"{hospital_name} hospital {city}"}

    try:
        response = await client.post(
            _PLACES_TEXT_SEARCH_URL,
            json=payload,
            headers={
                "X-Goog-Api-Key": settings.google_maps_api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.formattedAddress,places.location"
                ),
            },
            timeout=10.0,
        )
        if response.status_code != 200:
            return None
        body = response.json()
        places = body.get("places", [])
        if not places:
            return None

        place = places[0]
        location = place.get("location", {})
        lat = location.get("latitude")
        lng = location.get("longitude")
        if lat is None or lng is None:
            return None

        place_id = place.get("id", "")
        return HospitalCoordinates(
            latitude=float(lat),
            longitude=float(lng),
            google_maps_place_id=place_id or None,
            google_maps_url=(
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                if place_id
                else None
            ),
            formatted_address=place.get("formattedAddress"),
            coordinate_confidence=0.75,
        )
    except Exception:
        return None

"""
SWASTHYA AI CORE — Discovery API Router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_discovery_service
from src.dtos.discovery_dtos import DiscoverySearchRequest, DiscoverySearchResponse
from src.services.discovery_service import DiscoveryService

router = APIRouter(prefix="/api/discovery", tags=["Discovery"])


@router.post("/search", response_model=DiscoverySearchResponse)
async def start_discovery(
    request: DiscoverySearchRequest,
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoverySearchResponse:
    """
    Immediately creates a background discovery task.
    Returns a task_id that can be polled for progress.
    """
    return await service.start_discovery(request)

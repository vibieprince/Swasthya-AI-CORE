"""
SWASTHYA AI CORE — Discovery DTOs.

Data Transfer Objects for the POST /api/discovery/search endpoint.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from src.domain.context.models import PatientContext


class DiscoverySearchRequest(BaseModel):
    """
    Input payload for initiating a discovery search.
    Requires a full, validated PatientContext object from the Context API.
    """

    context: PatientContext = Field(..., description="The full patient context object")
    max_results: int = Field(default=4, ge=2, le=10, description="Max hospitals to return")
    correlation_id: Optional[str] = Field(None, description="Optional trace ID")


class DiscoverySearchResponse(BaseModel):
    """
    Output payload returned immediately after initiating discovery.
    Since discovery is asynchronous, this returns a task_id.
    """

    task_id: str = Field(..., description="Unique ID for polling task progress")
    status: str = Field(default="queued", description="Initial status")
    message: str = Field(default="Discovery task queued successfully")

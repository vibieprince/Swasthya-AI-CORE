"""
SWASTHYA AI CORE — Task DTOs.

Data Transfer Objects for the GET /api/tasks/{task_id}/progress endpoint.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from src.domain.tasks.models import TaskProgress


class TaskProgressResponse(BaseModel):
    """
    Output payload representing current task progress and result.
    """

    task_id: str
    status: str
    progress_percent: int = Field(ge=0, le=100)
    current_stage: str
    result: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, progress: TaskProgress) -> TaskProgressResponse:
        """Convert a Redis TaskProgress domain model into a Response DTO."""
        return cls(
            task_id=progress.task_id,
            status=progress.status.value,
            progress_percent=progress.progress_percent,
            current_stage=progress.current_stage,
            result=progress.result,
            error_message=progress.error_message,
            created_at=progress.created_at,
            updated_at=progress.updated_at,
        )

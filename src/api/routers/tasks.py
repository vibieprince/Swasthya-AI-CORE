"""
SWASTHYA AI CORE — Tasks API Router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_task_service
from src.dtos.task_dtos import TaskProgressResponse
from src.services.task_service import TaskService

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])


@router.get("/{task_id}/progress", response_model=TaskProgressResponse)
async def get_task_progress(
    task_id: str,
    service: TaskService = Depends(get_task_service),
) -> TaskProgressResponse:
    """
    Returns the progress and status of an asynchronous discovery task.
    """
    return await service.get_progress(task_id)

"""
SWASTHYA AI CORE — Task Service.

Reads task progress from Redis and maps to DTOs.
"""

from __future__ import annotations

from src.common.exceptions import SwasthyaBaseError, TaskNotFoundError
from src.common.logging import get_logger
from src.dtos.task_dtos import TaskProgressResponse
from src.infrastructure.redis.client import get_task_progress

logger = get_logger(__name__)


class TaskService:
    """
    Service for querying async task progress.
    """

    async def get_progress(self, task_id: str) -> TaskProgressResponse:
        """
        Retrieve task progress from Redis.
        """
        try:
            progress = await get_task_progress(task_id)
            return TaskProgressResponse.from_domain(progress)
        except TaskNotFoundError:
            logger.warning("Task not found", extra={"task_id": task_id})
            raise
        except Exception as exc:
            logger.error("Failed to fetch task progress", extra={"task_id": task_id, "error": str(exc)})
            raise SwasthyaBaseError("Failed to fetch task progress.") from exc

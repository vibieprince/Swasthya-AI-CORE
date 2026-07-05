"""
SWASTHYA AI CORE — Task Domain Models.

Redis-backed task progress tracking models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Lifecycle states of a discovery task."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskProgress(BaseModel):
    """
    Transient task progress stored in Redis with a 6-hour TTL.

    NEVER persisted to any permanent store.
    """

    task_id: str
    status: TaskStatus = TaskStatus.QUEUED
    progress_percent: int = Field(default=0, ge=0, le=100)
    current_stage: str = "Queued"
    result: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    correlation_id: str = ""

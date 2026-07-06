"""
SWASTHYA AI CORE — Async Job Executor.

Provides an internal async scheduler to execute the discovery pipeline
in the background without relying on an external queue like RabbitMQ.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from src.common.correlation import set_correlation_id
from src.common.logging import get_logger
from src.domain.discovery.models import DiscoveryRequest
from src.domain.ranking.models import RecommendationBundle
from src.domain.tasks.models import TaskStatus
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.redis.client import update_task_progress
from src.pipelines.discovery.orchestrator import DiscoveryOrchestrator
from src.ranking.explainer import RecommendationExplainer
from src.ranking.ranker import HospitalRanker

logger = get_logger(__name__)


class BaseJobExecutor(ABC):
    """Abstract interface for background job execution."""

    @abstractmethod
    def submit_discovery_task(self, request_data: dict[str, Any]) -> None:
        """Submit a discovery task for background execution."""
        pass


class AsyncIOJobExecutor(BaseJobExecutor):
    """
    In-memory async job executor using asyncio.create_task().
    Ideal for single-container deployment on Render Free.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway
        self._orchestrator = DiscoveryOrchestrator(gateway)
        self._ranker = HospitalRanker()
        self._explainer = RecommendationExplainer(gateway)
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def submit_discovery_task(self, request_data: dict[str, Any]) -> None:
        """
        Spawns a background coroutine to run the discovery pipeline.
        Maintains a strong reference in self._background_tasks to prevent
        the task from being garbage collected mid-execution.
        """
        task = asyncio.create_task(self._process_message(request_data))
        
        # Add to set for strong reference
        self._background_tasks.add(task)
        
        # Remove from set when done
        task.add_done_callback(self._background_tasks.discard)

        logger.info(
            "Background discovery task submitted internally", 
            extra={"active_tasks": len(self._background_tasks)}
        )

    async def _process_message(self, message_body: dict[str, Any]) -> None:
        """
        Handle one discovery task end-to-end.
        """
        try:
            request = DiscoveryRequest.model_validate(message_body)
        except Exception as exc:
            logger.error(
                "Invalid message payload — cannot process",
                extra={"error": str(exc), "keys": list(message_body.keys())},
            )
            return

        task_id = request.task_id

        if request.correlation_id:
            set_correlation_id(request.correlation_id)

        logger.info("Processing task", extra={"task_id": task_id})
        t_start = time.monotonic()

        async def _progress(percent: int, stage: str) -> None:
            try:
                await update_task_progress(task_id, TaskStatus.RUNNING, percent, stage)
            except Exception as exc:
                logger.warning(
                    "Progress update failed — continuing",
                    extra={"task_id": task_id, "stage": stage, "error": str(exc)},
                )

        try:
            # ── 10%: Planning ─────────────────────────────────────────────────
            await update_task_progress(task_id, TaskStatus.RUNNING, 10, "Planning")

            # ── 25–80%: Discovery (granular via progress_callback) ─────────────
            candidates = await self._orchestrator.discover(
                request, progress_callback=_progress
            )

            # ── 70%: Ranking ──────────────────────────────────────────────────
            await update_task_progress(task_id, TaskStatus.RUNNING, 70, "Ranking")
            t_rank = time.monotonic()
            ranked = self._ranker.rank(candidates, request)
            rank_ms = int((time.monotonic() - t_rank) * 1000)

            # ── 85%: Explanations ─────────────────────────────────────────────
            await update_task_progress(task_id, TaskStatus.RUNNING, 85, "Explanation")
            t_exp = time.monotonic()
            explained = await self._explainer.explain_all(ranked, request)
            exp_ms = int((time.monotonic() - t_exp) * 1000)

            # ── 100%: Done ────────────────────────────────────────────────────
            sources_used = sorted({c.source for c in candidates}) if candidates else []
            bundle = RecommendationBundle(
                task_id=task_id,
                context_id=request.context_id,
                specialty=request.specialty.value,
                location_searched=request.location.city,
                recommendations=explained,
                total_candidates_evaluated=len(candidates),
                pipeline_latency_ms=int((time.monotonic() - t_start) * 1000),
                sources_used=sources_used,
            )

            await update_task_progress(
                task_id, TaskStatus.COMPLETED, 100, "Completed", result=bundle
            )

            logger.info(
                "Task completed",
                extra={
                    "task_id": task_id,
                    "latency_ms": bundle.pipeline_latency_ms,
                    "timings": {
                        "ranking_ms": rank_ms,
                        "explanation_ms": exp_ms,
                    },
                    "recommendations": len(explained),
                },
            )

        except asyncio.CancelledError:
            logger.warning("Task cancelled by shutdown", extra={"task_id": task_id})
            await asyncio.shield(
                update_task_progress(
                    task_id,
                    TaskStatus.FAILED,
                    0,
                    "Cancelled",
                    error_message="Server shut down during processing — please retry.",
                )
            )

        except Exception as exc:
            logger.error(
                "Task failed",
                extra={"task_id": task_id, "error": str(exc)},
                exc_info=True,
            )
            try:
                await update_task_progress(
                    task_id,
                    TaskStatus.FAILED,
                    0,
                    "Failed",
                    error_message=f"{type(exc).__name__}: {str(exc)[:400]}",
                )
            except Exception as redis_exc:
                logger.error(
                    "Could not write FAILED status to Redis",
                    extra={"task_id": task_id, "error": str(redis_exc)},
                )

    async def shutdown(self) -> None:
        """Wait for all pending tasks to finish gracefully during app shutdown."""
        if not self._background_tasks:
            return
            
        logger.info(f"Waiting for {len(self._background_tasks)} background tasks to finish...")
        # Give background tasks 30 seconds to finish before forcing shutdown
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._background_tasks, return_exceptions=True),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning("Some background tasks did not finish in time during shutdown.")
        logger.info("Background tasks shutdown complete.")


# Global singleton management
_executor: AsyncIOJobExecutor | None = None

def initialize_job_executor(gateway: LLMGateway) -> None:
    """Initialize the global job executor."""
    global _executor
    if _executor is None:
        _executor = AsyncIOJobExecutor(gateway)

def get_job_executor() -> AsyncIOJobExecutor:
    """Returns the singleton JobExecutor."""
    global _executor
    if _executor is None:
        raise RuntimeError("JobExecutor is not initialized. Call initialize_job_executor first.")
    return _executor

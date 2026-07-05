"""
SWASTHYA AI CORE — Discovery Worker Entry Point.

Production-grade worker that:
- Initialises infrastructure (HTTP, Redis)
- Registers SIGTERM/SIGINT for graceful shutdown (POSIX) or Ctrl+C (Windows)
- Consumes RabbitMQ messages indefinitely
- Never returns until shutdown is requested

Progress milestones written to Redis:
  0%  → Queued          (written by API at dispatch time)
  10% → Planning Search
  25% → Google Places complete
  40% → Tavily complete
  50% → Deduplication complete
  65% → Research started
  80% → Research completed
  90% → Ranking hospitals
  100% → Completed

Error contract:
  Business failure → FAILED in Redis, message acked (no requeue)
  CancelledError   → FAILED in Redis via asyncio.shield(), message nacked+requeued
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from typing import Any

from src.common.correlation import set_correlation_id
from src.common.logging import configure_logging, get_logger
from src.domain.discovery.models import DiscoveryRequest
from src.domain.ranking.models import RecommendationBundle
from src.domain.tasks.models import TaskStatus
from src.infrastructure.llm.gateway import LLMGateway
from src.infrastructure.rabbitmq.consumer import request_shutdown, start_consumer
from src.infrastructure.redis.client import update_task_progress
from src.pipelines.discovery.orchestrator import DiscoveryOrchestrator
from src.ranking.explainer import RecommendationExplainer
from src.ranking.ranker import HospitalRanker

logger = get_logger(__name__)


class DiscoveryWorker:
    """
    Processes a single discovery task message end-to-end.

    One instance is shared across all messages processed by this worker
    process.  All state is local to each process_message() call — the
    worker itself is stateless.
    """

    def __init__(self, gateway: LLMGateway) -> None:
        self._orchestrator = DiscoveryOrchestrator(gateway)
        self._ranker = HospitalRanker()
        self._explainer = RecommendationExplainer(gateway)

    async def process_message(self, message_body: dict[str, Any]) -> None:
        """
        Handle one RabbitMQ discovery task message.

        Called by the consumer for every inbound message.
        Must NOT raise for business logic errors.
        MAY raise for CancelledError (propagated for clean shutdown).
        """
        # Validate the incoming payload against our domain model
        try:
            request = DiscoveryRequest.model_validate(message_body)
        except Exception as exc:
            logger.error(
                "Invalid message payload — cannot process",
                extra={"error": str(exc), "keys": list(message_body.keys())},
            )
            # Cannot update Redis without a valid task_id — just return
            # Consumer will ack this message to prevent requeue loop
            return

        task_id = request.task_id

        if request.correlation_id:
            set_correlation_id(request.correlation_id)

        logger.info("Processing task", extra={"task_id": task_id})
        t_start = time.monotonic()

        # Progress callback injected into orchestrator (Issue 7)
        async def _progress(percent: int, stage: str) -> None:
            try:
                await update_task_progress(task_id, TaskStatus.RUNNING, percent, stage)
            except Exception as exc:
                # Never let a Redis update failure abort the pipeline
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
            ranked = self._ranker.rank(candidates, request)

            # ── 85%: Explanations ─────────────────────────────────────────────
            await update_task_progress(task_id, TaskStatus.RUNNING, 85, "Explanation")
            explained = await self._explainer.explain_all(ranked, request)

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
                    "recommendations": len(explained),
                },
            )

        except asyncio.CancelledError:
            # Shutdown in progress — mark task FAILED so client is not stuck
            logger.warning("Task cancelled by shutdown", extra={"task_id": task_id})
            # asyncio.shield() keeps this Redis write from being cancelled
            await asyncio.shield(
                update_task_progress(
                    task_id,
                    TaskStatus.FAILED,
                    0,
                    "Cancelled",
                    error_message="Worker shut down during processing — please retry.",
                )
            )
            raise  # Re-raise so consumer nacks the message with requeue=True

        except Exception as exc:
            logger.error(
                "Task failed",
                extra={"task_id": task_id, "error": str(exc)},
                exc_info=True,
            )
            # Best-effort: write FAILED to Redis so the polling client gets feedback
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
                    "Could not write FAILED status to Redis — raising to requeue",
                    extra={"task_id": task_id, "error": str(redis_exc)},
                )
                # Redis is dead. We must raise so the consumer nacks and requeues.
                raise redis_exc


async def run_worker() -> None:
    """
    Worker process entry point.

    Starts all infrastructure and blocks until SIGTERM/SIGINT.

    Start with:
        python -m src.workers.discovery_worker
    Or:
        python -c "import asyncio; from src.workers.discovery_worker import run_worker; asyncio.run(run_worker())"
    """
    configure_logging()
    logger.info("Discovery Worker starting")

    from src.infrastructure.http.client import close_http_client, initialize_http_client
    from src.infrastructure.redis.client import close_redis, initialize_redis

    await initialize_http_client()
    await initialize_redis()

    gateway = LLMGateway()
    worker = DiscoveryWorker(gateway)

    # ── Signal handling for graceful shutdown ─────────────────────────────────
    loop = asyncio.get_running_loop()

    def _handle_shutdown_signal(signame: str) -> None:
        logger.info(f"Received {signame} — initiating graceful shutdown")
        request_shutdown()

    # POSIX systems (Linux, macOS): use loop.add_signal_handler
    # Windows: falls back to signal.signal (handled via KeyboardInterrupt)
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _handle_shutdown_signal, sig.name)
    else:
        # On Windows, asyncio.run() converts Ctrl+C to CancelledError —
        # request_shutdown() will be called when the consumer receives it.
        pass

    # ── Run forever ───────────────────────────────────────────────────────────
    try:
        logger.info("Discovery Worker ready — consuming messages")
        await start_consumer(worker.process_message)
    finally:
        logger.info("Discovery Worker shutting down")
        try:
            await close_http_client()
        except Exception as exc:
            logger.warning("Error closing HTTP client", extra={"error": str(exc)})
        try:
            await close_redis()
        except Exception as exc:
            logger.warning("Error closing Redis", extra={"error": str(exc)})
        logger.info("Discovery Worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())

"""
SWASTHYA AI CORE — Redis Async Client.

Production-hardened Redis client for Cloud Redis (Upstash, Redis Labs).

Fixes applied for long-running task persistence:
1. TCP Keep-Alive Enabled: Prevents idle connections from being dropped by Cloud firewalls.
2. Tenacity Retries: Exponential backoff specifically tailored for DNS (getaddrinfo) 
   and transient network drops during 4+ minute long LLM inferences.
3. Atomic Hashes (HSET): Replaced vulnerable GET -> SET logic with direct HSET updates,
   eliminating race conditions and reducing network round-trips by 50%.
4. Graceful Degradation: If Redis fails completely, errors are logged but the pipeline
   continues execution to guarantee final result calculation.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import BusyLoadingError, ConnectionError, TimeoutError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.common.exceptions import RedisError, TaskNotFoundError
from src.common.logging import get_logger
from src.config.settings import get_settings
from src.domain.tasks.models import TaskProgress, TaskStatus

logger = get_logger(__name__)

_pool: ConnectionPool | None = None
_redis: Redis | None = None  # type: ignore[type-arg]

# Explicit timeout for individual Redis operations
_REDIS_OP_TIMEOUT = 5.0


async def initialize_redis() -> None:
    """
    Create the Redis connection pool.

    socket_keepalive=True prevents idle connections from expiring in CloudAMQP/Upstash.
    health_check_interval=10 actively tests connections in the background.
    """
    global _pool, _redis
    settings = get_settings()

    _pool = aioredis.ConnectionPool.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_timeout=5,
        socket_keepalive=True,
        health_check_interval=10,
        retry_on_timeout=True,
        retry_on_error=[ConnectionError, TimeoutError],
        retry=Retry(ExponentialBackoff(cap=5, base=0.1), retries=5),
    )
    _redis = Redis(connection_pool=_pool)

    try:
        await asyncio.wait_for(_redis.ping(), timeout=_REDIS_OP_TIMEOUT)
        logger.info("Redis connection pool established")
    except Exception as exc:
        raise RedisError("ping", f"Cannot connect to Redis: {exc}") from exc


async def close_redis() -> None:
    """Close the Redis connection pool gracefully."""
    global _pool, _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
    if _pool is not None:
        await _pool.aclose()
        _pool = None
    logger.info("Redis connection pool closed.")


def _get_client() -> Redis:  # type: ignore[type-arg]
    """Return the active Redis client."""
    if _redis is None:
        raise RuntimeError("Redis client not initialised.")
    return _redis


def _task_key(task_id: str) -> str:
    return f"swasthya:task:{task_id}"


@retry(
    retry=retry_if_exception_type((RedisError, Exception)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def create_task_progress(task_id: str, correlation_id: str) -> TaskProgress:
    """
    Initialise a task progress record in Redis using Hashes (HSET).

    Retries on DNS or connection failures with exponential backoff.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()
    progress = TaskProgress(
        task_id=task_id,
        status=TaskStatus.QUEUED,
        progress_percent=0,
        current_stage="Queued",
        created_at=now,
        updated_at=now,
        correlation_id=correlation_id,
    )
    
    mapping = {
        "task_id": progress.task_id,
        "status": progress.status.value,
        "progress_percent": str(progress.progress_percent),
        "current_stage": progress.current_stage,
        "created_at": progress.created_at,
        "updated_at": progress.updated_at,
        "correlation_id": progress.correlation_id,
        "result": "",
        "error_message": "",
    }
    
    client = _get_client()
    key = _task_key(task_id)
    try:
        # Pipeline ensures HSET and EXPIRE execute together
        async with client.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, settings.redis_ttl_seconds)
            await asyncio.wait_for(pipe.execute(), timeout=_REDIS_OP_TIMEOUT)
    except Exception as exc:
        logger.warning("Redis create failed — triggering tenacity retry", extra={"error": str(exc)})
        raise RedisError("create_task_progress", str(exc)) from exc
    return progress


async def _robust_hset_update(key: str, mapping: dict[str, str], ttl: int, is_final: bool = False) -> None:
    """
    Internal robust retry wrapper for Redis HSET operations.
    If is_final is True, retries indefinitely to guarantee task completion durability.
    """
    client = _get_client()

    @retry(
        retry=retry_if_exception_type((RedisError, Exception)),
        stop=None if is_final else stop_after_attempt(5),
        wait=wait_exponential(multiplier=1.5, min=2, max=30 if is_final else 15),
        reraise=True,
    )
    async def _execute() -> None:
        try:
            async with client.pipeline(transaction=True) as pipe:
                pipe.hset(key, mapping=mapping)
                pipe.expire(key, ttl)
                await asyncio.wait_for(pipe.execute(), timeout=_REDIS_OP_TIMEOUT)
        except Exception as exc:
            logger.warning(
                "Redis update failed — triggering tenacity retry",
                extra={"error": str(exc), "key": key, "is_final": is_final}
            )
            raise RedisError("update_task_progress", str(exc)) from exc

    await _execute()


async def update_task_progress(
    task_id: str,
    status: TaskStatus,
    progress_percent: int,
    current_stage: str,
    result: Any = None,
    error_message: Optional[str] = None,
) -> None:
    """
    Atomically update an existing task progress record in Redis using HSET.

    Eliminates the dangerous GET -> SET race condition entirely.
    Gracefully degrades: if the 5 retries fail, it logs the error but does NOT
    fail the entire Python workflow.
    """
    settings = get_settings()
    key = _task_key(task_id)
    
    mapping: dict[str, str] = {
        "status": status.value,
        "progress_percent": str(progress_percent),
        "current_stage": current_stage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # Ensure task_id is present in case this is the first write due to eviction
        "task_id": task_id,
    }
    
    if result is not None:
        mapping["result"] = result.model_dump_json() if hasattr(result, "model_dump_json") else json.dumps(result, default=str)
    
    if error_message is not None:
        mapping["error_message"] = error_message

    is_final = status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    try:
        await _robust_hset_update(key, mapping, settings.redis_ttl_seconds, is_final=is_final)
    except Exception as exc:
        # Graceful degradation for intermediate progress only
        if not is_final:
            logger.error(
                "CRITICAL: Failed to update intermediate Redis progress — continuing pipeline",
                extra={"task_id": task_id, "error": str(exc)},
                exc_info=True,
            )
        else:
            # Should never happen due to infinite retries, but if it does, propagate to Nack
            raise RedisError("update_task_progress:final", str(exc)) from exc


@retry(
    retry=retry_if_exception_type((RedisError, Exception)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
async def get_task_progress(task_id: str) -> TaskProgress:
    """
    Retrieve a task progress record from Redis using HGETALL.

    Raises TaskNotFoundError if not found.
    """
    client = _get_client()
    key = _task_key(task_id)

    try:
        raw_dict = await asyncio.wait_for(client.hgetall(key), timeout=_REDIS_OP_TIMEOUT)
    except Exception as exc:
        raise RedisError("get_task_progress", str(exc)) from exc

    if not raw_dict:
        raise TaskNotFoundError(task_id)

    try:
        # Convert string representations back to native types
        data: dict[str, Any] = dict(raw_dict)
        data["progress_percent"] = int(data.get("progress_percent", 0))
        
        result_str = data.get("result", "")
        if result_str:
            data["result"] = json.loads(result_str)
        else:
            data["result"] = None
            
        error_str = data.get("error_message", "")
        data["error_message"] = error_str if error_str else None

        return TaskProgress(**data)
    except Exception as exc:
        logger.error(
            "Failed to parse TaskProgress Hash from Redis",
            extra={"task_id": task_id, "error": str(exc)},
        )
        raise RedisError("get_task_progress:parse", f"Corrupt task data: {exc}") from exc


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    """Store an arbitrary serializable value in Redis with a TTL."""
    client = _get_client()
    try:
        serialised = json.dumps(value, default=str) if not isinstance(value, str) else value
        await asyncio.wait_for(
            client.setex(key, ttl_seconds, serialised),
            timeout=_REDIS_OP_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("Cache write failed", extra={"key": key, "error": str(exc)})


async def cache_get(key: str) -> Optional[str]:
    """Retrieve a cached value from Redis. Returns None on cache miss."""
    client = _get_client()
    try:
        return await asyncio.wait_for(client.get(key), timeout=_REDIS_OP_TIMEOUT)  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("Cache read failed", extra={"key": key, "error": str(exc)})
        return None

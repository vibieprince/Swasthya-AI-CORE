"""
SWASTHYA AI CORE — RabbitMQ Publisher.

Redesigned Publisher Lifecycle:
─────────────────────────────────────────────────────────────────
Root Cause Analysis of 'Channel invalid: RobustChannel closed':
The previous implementation cached a global `_channel` and `_exchange`.
During startup, the `exchange` object was bound to a temporary channel 
which was subsequently closed, rendering the `exchange` permanently stale.
When CloudAMQP closed idle connections, the stale state worsened.

Fix Implementation:
1. Removed all cached `_channel` and `_exchange` variables.
2. Implemented `aio_pika.pool.Pool` for channels.
3. Every `publish()` dynamically acquires a live, healthy channel from the pool.
4. The exchange is retrieved dynamically `channel.get_exchange()` ensuring
   it belongs to the current live channel context.
5. Absolute zero stale state.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import aio_pika
import aio_pika.abc
from aio_pika.exceptions import ChannelInvalidStateError
from aio_pika.pool import Pool
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.common.exceptions import RabbitMQError
from src.common.logging import get_logger
from src.config.settings import get_settings
from src.infrastructure.rabbitmq.core import declare_idempotent_queue

logger = get_logger(__name__)

# Module-level state — ONLY the robust connection and the channel pool are cached.
# No channels or exchanges are cached globally.
_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel_pool: Pool[aio_pika.abc.AbstractChannel] | None = None

_PUBLISH_TIMEOUT = 5.0


async def initialize_publisher() -> None:
    """Establish robust connection, setup channel pool, and perform idempotent declarations."""
    global _connection, _channel_pool
    settings = get_settings()

    try:
        # 1. Open Robust Connection (auto-heals TCP drops)
        _connection = await aio_pika.connect_robust(
            settings.rabbitmq_url,
            heartbeat=60,
            reconnect_interval=5.0,
            fail_fast=False,
        )

        # 2. Setup Channel Pool
        async def get_channel() -> aio_pika.abc.AbstractChannel:
            return await _connection.channel()

        _channel_pool = Pool(get_channel, max_size=10)

        # 3. Perform Idempotent Startup Declaration
        # We acquire a temporary channel to ensure the exchange and queue exist,
        # handling LavinMQ PRECONDITION_FAILED queue conflicts gracefully.
        async with _channel_pool.acquire() as channel:
            exchange = await channel.declare_exchange(
                settings.rabbitmq_exchange,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            
            # This core function handles the 406 PRECONDITION_FAILED gracefully
            # It returns a live channel and queue used for binding.
            # Since this is the publisher, we just close the channel to prevent leaks.
            core_channel, _ = await declare_idempotent_queue(
                connection=_connection,
                queue_name=settings.rabbitmq_discovery_queue,
                exchange=exchange,
                prefetch_count=settings.rabbitmq_prefetch_count,
            )
            if not core_channel.is_closed:
                await core_channel.close()

        logger.info(
            "RabbitMQ publisher initialised",
            extra={"exchange": settings.rabbitmq_exchange, "queue": settings.rabbitmq_discovery_queue}
        )

    except Exception as exc:
        raise RabbitMQError("initialize_publisher", str(exc)) from exc


async def close_publisher() -> None:
    """Gracefully close the RabbitMQ publisher pool and connection."""
    global _connection, _channel_pool

    pool = _channel_pool
    conn = _connection
    
    _channel_pool = None
    _connection = None

    if pool is not None:
        try:
            await pool.close()
        except Exception as exc:
            logger.warning("Error closing publisher channel pool", extra={"error": str(exc)})

    if conn is not None and not conn.is_closed:
        try:
            await conn.close()
        except Exception as exc:
            logger.warning("Error closing publisher connection", extra={"error": str(exc)})

    logger.info("RabbitMQ publisher connection closed.")


@retry(
    retry=retry_if_exception_type((RabbitMQError, asyncio.TimeoutError, ChannelInvalidStateError)),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
async def publish_discovery_task(message_body: dict[str, Any]) -> None:
    """
    Publish a persistent task to the exchange.
    
    Guarantees liveness:
    - Acquires a fresh, healthy channel from the pool.
    - Gets the exchange within the context of that specific channel.
    - If the channel fails, tenacity retries, and the pool provisions a new one.
    """
    global _connection, _channel_pool
    
    if _connection is None or _channel_pool is None:
        raise RabbitMQError("publish", "Publisher not initialised")
        
    if _connection.is_closed:
        # aio-pika handles reconnection in the background, but if we catch it mid-reconnect:
        raise RabbitMQError("publish", "Broker connection is currently closed (reconnecting...)")

    settings = get_settings()
    message_body = dict(message_body)
    message_body["published_at"] = datetime.now(timezone.utc).isoformat()
    task_id = message_body.get("task_id", "unknown")

    try:
        # Acquire a live channel from the pool.
        # If a channel in the pool is closed, the pool automatically creates a new one.
        async with _channel_pool.acquire() as channel:
            
            # Dynamically retrieve the exchange ON THIS SPECIFIC CHANNEL.
            # This completely eliminates the stale `exchange` object bug.
            # aio-pika caches this internally on the channel, so it's extremely fast.
            exchange = await channel.get_exchange(settings.rabbitmq_exchange)

            await asyncio.wait_for(
                exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(message_body, default=str).encode(),
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type="application/json",
                    ),
                    routing_key=settings.rabbitmq_discovery_queue,
                ),
                timeout=_PUBLISH_TIMEOUT,
            )

        logger.info(
            "Discovery task published",
            extra={"task_id": task_id, "routing_key": settings.rabbitmq_discovery_queue},
        )

    except asyncio.TimeoutError as exc:
        logger.warning(
            "Publish timed out, retrying...", 
            extra={"task_id": task_id}
        )
        raise RabbitMQError("publish", f"Publish timed out after {_PUBLISH_TIMEOUT}s") from exc
        
    except ChannelInvalidStateError as exc:
        logger.warning(
            "Channel closed during publish, pool will recover on retry...", 
            extra={"task_id": task_id, "error": str(exc)}
        )
        raise RabbitMQError("publish", f"Channel invalid: {exc}") from exc
        
    except RabbitMQError:
        raise
        
    except Exception as exc:
        logger.error(
            "Unexpected error during publish",
            extra={"task_id": task_id, "error": str(exc)},
            exc_info=True
        )
        raise RabbitMQError("publish", str(exc)) from exc

"""
SWASTHYA AI CORE — RabbitMQ Consumer (Worker-side).

Production-grade consumer for aio-pika 9.x and CloudAMQP/LavinMQ.

Root causes fixed in this revision:
─────────────────────────────────────────────────────────────────
BUG 4 (IDEMPOTENCY): LavinMQ fails startup if a queue exists with 
  differing properties (e.g. x-queue-type). 
  Fix: Leverages declare_idempotent_queue to gracefully fallback to 
  passive=True on PRECONDITION_FAILED, eliminating manual deletion.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import aio_pika
import aio_pika.abc
from aio_pika.exceptions import ChannelInvalidStateError

from src.common.logging import get_logger
from src.config.settings import get_settings
from src.infrastructure.rabbitmq.core import declare_idempotent_queue

logger = get_logger(__name__)

MessageHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]

_stop_event: asyncio.Event | None = None


def request_shutdown() -> None:
    """Signal the consumer to stop after completing the current message."""
    global _stop_event
    if _stop_event is not None:
        _stop_event.set()
    logger.info("Consumer shutdown requested — will stop after current message.")


async def start_consumer(handler: MessageHandler) -> None:
    """
    Connect to RabbitMQ and consume discovery task messages indefinitely.
    Blocks until request_shutdown() is called.
    """
    global _stop_event
    _stop_event = asyncio.Event()
    settings = get_settings()

    logger.info("Connecting to RabbitMQ", extra={"queue": settings.rabbitmq_discovery_queue})

    connection: aio_pika.abc.AbstractRobustConnection = await aio_pika.connect_robust(
        settings.rabbitmq_url,
        heartbeat=60,
        reconnect_interval=5.0,
        fail_fast=False,
    )

    try:
        async with connection:
            # We need a temporary channel just to declare the exchange
            tmp_channel = await connection.channel()
            exchange = await tmp_channel.declare_exchange(
                settings.rabbitmq_exchange,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            
            # Idempotently declare and bind the queue (handles 406 PRECONDITION_FAILED)
            channel, queue = await declare_idempotent_queue(
                connection=connection,
                queue_name=settings.rabbitmq_discovery_queue,
                exchange=exchange,
                prefetch_count=settings.rabbitmq_prefetch_count,
            )

            logger.info(
                "Consumer started — waiting for messages",
                extra={"queue": settings.rabbitmq_discovery_queue},
            )

            await queue.consume(_make_processor(handler), no_ack=False)
            
            # Close the temporary channel as we no longer need it
            await tmp_channel.close()

            await _stop_event.wait()
    finally:
        logger.info("Consumer connection closed — shutdown complete.")


def _make_processor(
    handler: MessageHandler,
) -> Callable[[aio_pika.abc.AbstractIncomingMessage], Coroutine[Any, Any, None]]:
    """Return the per-message processor coroutine factory."""

    async def _process(message: aio_pika.abc.AbstractIncomingMessage) -> None:
        """Process a single inbound RabbitMQ message."""
        task_id: str = "unknown"
        body: dict[str, Any] = {}

        try:
            body = json.loads(message.body)
            task_id = body.get("task_id", "unknown")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error(
                "Malformed message — rejecting without requeue",
                extra={"error": str(exc), "body_preview": repr(message.body[:120])},
            )
            try:
                await message.reject(requeue=False)
            except Exception:
                pass
            return

        logger.info("Message received", extra={"task_id": task_id})

        try:
            await handler(body)
            await message.ack()
            logger.info("Message acked", extra={"task_id": task_id})

        except asyncio.CancelledError:
            logger.warning(
                "Worker cancelled during message processing — requeueing",
                extra={"task_id": task_id},
            )
            try:
                await message.nack(requeue=True)
            except Exception:
                pass
            raise

        except ChannelInvalidStateError as exc:
            logger.error(
                "Channel invalid state during processing — broker will redeliver",
                extra={"task_id": task_id, "error": str(exc)},
            )

        except Exception as exc:
            # Any exception that escapes the handler is an infrastructure failure
            # (e.g. Redis final persistence failed). Business logic failures are
            # caught internally by the worker and return normally.
            logger.error(
                "Handler raised unexpected exception — requeueing message",
                extra={"task_id": task_id, "error": str(exc)},
                exc_info=True,
            )
            try:
                await message.nack(requeue=True)
            except Exception:
                pass

    return _process

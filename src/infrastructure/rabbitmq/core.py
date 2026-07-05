"""
SWASTHYA AI CORE — RabbitMQ Core Utilities.

Shared robust queue declaration logic for publishers and consumers.
Guarantees idempotent startup even if queue properties change in LavinMQ/CloudAMQP.
"""

from __future__ import annotations

import aio_pika
import aio_pika.abc

from src.common.logging import get_logger

logger = get_logger(__name__)


async def declare_idempotent_queue(
    connection: aio_pika.abc.AbstractRobustConnection,
    queue_name: str,
    exchange: aio_pika.abc.AbstractExchange,
    prefetch_count: int,
) -> tuple[aio_pika.abc.AbstractChannel, aio_pika.abc.AbstractQueue]:
    """
    Safely declare and bind a queue, recovering gracefully if properties mismatch.

    LavinMQ/CloudAMQP strictly enforces queue properties. If a durable queue exists
    (e.g., with x-queue-type='classic') and we try to declare it without that arg,
    the broker throws 406 PRECONDITION_FAILED and forcibly closes the channel.

    This function catches that failure, opens a NEW channel, and binds to the
    existing queue passively, guaranteeing startup never fails.
    """
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=prefetch_count)

    try:
        # First attempt: declare exactly as we want it going forward.
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            passive=False,
            auto_delete=False,
        )
    except Exception as exc:
        err_str = str(exc).upper()
        if "PRECONDITION_FAILED" in err_str or "406" in err_str:
            logger.warning(
                "Queue properties mismatch (PRECONDITION_FAILED) — connecting passively",
                extra={"queue": queue_name, "error": str(exc)},
            )
            # The previous channel is now dead. We MUST open a new one.
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=prefetch_count)

            # Re-declare exchange on the new channel to be safe
            exchange = await channel.declare_exchange(
                exchange.name,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )

            # Second attempt: passive=True means "just connect to what is there"
            # It will not try to create it or enforce properties.
            queue = await channel.declare_queue(queue_name, passive=True)
        else:
            raise

    # Bind the queue to the exchange
    await queue.bind(exchange, routing_key=queue_name)
    return channel, queue

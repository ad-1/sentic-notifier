"""RabbitMQ consumer for the Sentic Notifier.

Connects to RabbitMQ using aio-pika, listens on the `notifications` queue,
deserialises each message into a NotificationPayload, and dispatches it via
TelegramNotifier.

Delivery semantics:
  - Message is acked after a successful (or best-effort) Telegram dispatch.
  - Message is rejected (requeue=False) only on payload validation failure,
    so malformed messages route to the dead-letter queue if one is configured.
  - Telegram API errors are logged but do not nack — an immediate retry would
    fail for the same reason. Dead-lettering / retry should be handled at the
    RabbitMQ topology level.
"""

import asyncio
import logging

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from sentic_notifier.models import NotificationPayload
from sentic_notifier.notifier.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """Async RabbitMQ consumer that dispatches NotificationPayload messages.

    Args:
        amqp_url:       Full AMQP connection URL, e.g.
                        ``amqp://user:password@rabbitmq-host:5672/vhost``
        queue_name:     Name of the queue to consume from. The queue must
                        already exist (managed by the topology operator).
        notifier:       Configured TelegramNotifier instance.
        prefetch_count: Number of unacked messages to hold at once. Keep at 1
                        to ensure at-most-one-in-flight per consumer instance.
    """

    def __init__(
        self,
        *,
        amqp_url: str,
        queue_name: str,
        notifier: TelegramNotifier,
        prefetch_count: int = 1,
    ) -> None:
        self._amqp_url = amqp_url
        self._queue_name = queue_name
        self._notifier = notifier
        self._prefetch_count = prefetch_count

    async def run(self) -> None:
        """Connect and start consuming. Blocks until cancelled.

        Uses connect_robust so that transient broker restarts are handled
        transparently without crashing the consumer process.
        """
        logger.info("Connecting to RabbitMQ (queue=%s)", self._queue_name)
        connection = await aio_pika.connect_robust(self._amqp_url)

        async with connection:
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=self._prefetch_count)

            # passive=True: the queue must already exist (owned by the topology
            # operator). The consumer should never create infrastructure.
            queue = await channel.declare_queue(
                self._queue_name,
                durable=True,
                passive=True,
            )

            logger.info("Consuming from queue '%s'", self._queue_name)
            async with queue.iterator() as messages:
                async for message in messages:
                    await self._handle(message)

    async def _handle(self, message: AbstractIncomingMessage) -> None:
        """Process a single incoming message."""
        try:
            payload = NotificationPayload.model_validate_json(message.body)
        except Exception as exc:
            logger.error(
                "Rejecting malformed message (delivery_tag=%s): %s",
                message.delivery_tag,
                exc,
            )
            await message.reject(requeue=False)
            return

        logger.debug(
            "Received notification id=%s source=%s ticker=%s",
            payload.id,
            payload.source,
            payload.ticker,
        )

        success = self._notifier.send_signal(payload)
        if not success:
            logger.warning(
                "Telegram dispatch failed for notification id=%s ticker=%s",
                payload.id,
                payload.ticker,
            )

        await message.ack()

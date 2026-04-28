import asyncio
import logging
import os

from sentic_notifier.consumer.rabbitmq_consumer import RabbitMQConsumer
from sentic_notifier.notifier.telegram import TelegramNotifier
from sentic_notifier.models import NotificationPayload, NewsItem


logger = logging.getLogger(__name__)


def _dispatch_to_telegram(items: list[NewsItem], config: dict) -> None:
    """Directly dispatch news items as Telegram signals (no-broker fallback)."""
    notifier = TelegramNotifier(
        bot_token=config["telegram_bot_token"],
        chat_id=config["telegram_chat_id"],
        dry_run=config["dry_run"],
    )
    signals = [
        NotificationPayload(
            ticker=item.ticker,
            headline=item.headline,
            url=item.url,
            provider_sentiment=item.provider_sentiment,
            published=item.published,
            summary=item.summary,
            source="sentic-signal",
        )
        for item in items
    ]
    sent = notifier.send_batch(signals)
    logger.info("Dispatched %d / %d signals via Telegram.", sent, len(signals))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    amqp_url = os.environ["AMQP_URL"]
    queue_name = os.environ.get("NOTIFICATIONS_QUEUE", "notifications")
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    notifier = TelegramNotifier(
        bot_token=bot_token,
        chat_id=chat_id,
        dry_run=dry_run,
    )
    consumer = RabbitMQConsumer(
        amqp_url=amqp_url,
        queue_name=queue_name,
        notifier=notifier,
    )

    logger.info("Sentic Notifier starting (queue=%s, dry_run=%s)", queue_name, dry_run)
    asyncio.run(consumer.run())


if __name__ == "__main__":
    main()
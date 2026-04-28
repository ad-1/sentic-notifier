"""Telegram notification dispatcher.

Sends Signal objects to a Telegram chat via the Bot API's sendMessage endpoint.

Configuration (via environment variables):
    TELEGRAM_BOT_TOKEN  — Bot token obtained from @BotFather.
    TELEGRAM_CHAT_ID    — Target chat/channel ID (e.g. your personal chat or a
                          private channel). Use a negative ID for group chats.

Message format (MarkdownV2):
    📡 *AAPL* | Bullish
    🗞 Apple announces record buyback programme
    📅 2026-04-13 13:00 UTC
    🔗 https://example.com/article
"""

import logging
from urllib.parse import urljoin

import requests

from sentic_notifier.models import NotificationPayload, SentimentLabel

logger = logging.getLogger(__name__)

_BOT_API_BASE = "https://api.telegram.org/bot{token}/"
_REQUEST_TIMEOUT = 10  # seconds

# Sentiment → emoji mapping for human-readable alerts.
_SENTIMENT_EMOJI: dict[SentimentLabel | None, str] = {
    SentimentLabel.BULLISH: "🟢",
    SentimentLabel.SOMEWHAT_BULLISH: "🟡",
    SentimentLabel.NEUTRAL: "⚪️",
    SentimentLabel.SOMEWHAT_BEARISH: "🟠",
    SentimentLabel.BEARISH: "🔴",
    None: "❓",
}


class TelegramNotifier:
    """Dispatches Signal alerts to a configured Telegram chat.

    Args:
        bot_token: Telegram bot token from @BotFather.
        chat_id:   Target chat/channel ID as a string.
        dry_run:   When True, log the message instead of sending it.
                   Useful in CI and test environments.
    """

    def __init__(self, bot_token: str, chat_id: str, *, dry_run: bool = False) -> None:
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must not be empty.")
        if not chat_id:
            raise ValueError("TELEGRAM_CHAT_ID must not be empty.")

        self._bot_token = bot_token
        self._chat_id = chat_id
        self._dry_run = dry_run
        self._base_url = _BOT_API_BASE.format(token=bot_token)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_signal(self, signal: NotificationPayload) -> bool:
        """Format and dispatch a single Signal to Telegram.

        Returns:
            True if the message was sent (or dry-run logged) successfully,
            False if the Telegram API returned an error.
        """
        message = _format_message(signal)

        if self._dry_run:
            logger.info("[DRY RUN] Telegram message:\n%s", message)
            return True

        return self._send_message(message)

    def send_batch(self, signals: list[NotificationPayload]) -> int:
        """Send multiple signals; returns the count of successful dispatches."""
        sent = 0
        for signal in signals:
            if self.send_signal(signal):
                sent += 1
        return sent

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _send_message(self, text: str) -> bool:
        """POST a message to the Telegram Bot API.

        Uses MarkdownV2 parse mode. Returns True on HTTP 200 + ok=true.
        """
        url = urljoin(self._base_url, "sendMessage")
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Telegram API request failed: %s", exc)
            return False

        body = response.json()
        if not body.get("ok"):
            logger.error("Telegram API error: %s", body.get("description", "unknown"))
            return False

        logger.info("Telegram alert sent for %s: %s", payload.get("chat_id"), text[:60])
        return True


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _format_message(signal: NotificationPayload) -> str:
    emoji = _SENTIMENT_EMOJI.get(signal.provider_sentiment, "❓")
    sentiment_label = signal.provider_sentiment.value if signal.provider_sentiment else "Unknown"
    published_str = signal.published.strftime("%Y-%m-%d %H:%M UTC")

    # Use a Markdown link [Link Text](URL)
    # Inside (url), we only strictly need to escape ')' and '\'
    safe_url = str(signal.url).replace("\\", "\\\\").replace(")", "\\)")
    
    return (
        f"📡 *{_escape(signal.ticker)}* \\| {_escape(sentiment_label)} {emoji}\n"
        f"🗞 {_escape(signal.headline)}\n"
        f"📅 {_escape(published_str)}\n"
        f"🔗 [Read Article]({safe_url})"
    )


_MARKDOWNV2_SPECIAL = "_*[]()~`>#+-=|{}.!"


def _escape(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    # Backslash must be handled first — otherwise it double-escapes other chars.
    text = text.replace("\\", "\\\\")
    for ch in _MARKDOWNV2_SPECIAL:
        text = text.replace(ch, f"\\{ch}")
    return text

"""Unit tests for the Telegram notifier module.

These tests use no real network calls — all HTTP is mocked via pytest-mock.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from sentic_notifier.models import NotificationPayload, SentimentLabel
from sentic_notifier.notifier.telegram import TelegramNotifier, _escape, _format_message


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_signal() -> NotificationPayload:
    return NotificationPayload(
        ticker="AAPL",
        headline="Apple announces record share buyback",
        url="https://example.com/apple-buyback",
        provider_sentiment=SentimentLabel.BULLISH,
        published=datetime(2026, 4, 13, 13, 0, 0, tzinfo=UTC),
        summary="Apple Inc. unveiled a $100B buyback programme.",
    )


@pytest.fixture()
def notifier() -> TelegramNotifier:
    return TelegramNotifier(
        bot_token="test-token-123",
        chat_id="987654321",
    )


@pytest.fixture()
def dry_run_notifier() -> TelegramNotifier:
    return TelegramNotifier(
        bot_token="test-token-123",
        chat_id="987654321",
        dry_run=True,
    )


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestTelegramNotifierInit:
    def test_raises_if_token_empty(self) -> None:
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            TelegramNotifier(bot_token="", chat_id="123")

    def test_raises_if_chat_id_empty(self) -> None:
        with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
            TelegramNotifier(bot_token="token", chat_id="")


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

class TestFormatMessage:
    def test_contains_ticker(self, sample_signal: NotificationPayload) -> None:
        message = _format_message(sample_signal)
        assert "AAPL" in message

    def test_contains_sentiment_label(self, sample_signal: NotificationPayload) -> None:
        message = _format_message(sample_signal)
        assert "Bullish" in message

    def test_contains_url(self, sample_signal: NotificationPayload) -> None:
        message = _format_message(sample_signal)
        assert "https://example.com/apple-buyback" in message

    def test_contains_published_date(self, sample_signal: NotificationPayload) -> None:
        # Hyphens are escaped in MarkdownV2 — check for year and time instead.
        message = _format_message(sample_signal)
        assert "2026" in message
        assert "13:00 UTC" in message

    def test_none_sentiment_shows_unknown(self, sample_signal: NotificationPayload) -> None:
        sample_signal.provider_sentiment = None
        message = _format_message(sample_signal)
        assert "Unknown" in message


class TestEscape:
    def test_escapes_dot(self) -> None:
        assert _escape("3.5%") == "3\\.5%"

    def test_escapes_hyphen(self) -> None:
        assert _escape("pre-market") == "pre\\-market"

    def test_escapes_parens(self) -> None:
        assert _escape("(test)") == "\\(test\\)"

    def test_no_double_escape_on_already_escaped(self) -> None:
        # A raw backslash in input should be escaped to \\ — not quadrupled.
        assert _escape("a\\b") == "a\\\\b"

    def test_plain_text_unchanged(self) -> None:
        assert _escape("AAPL") == "AAPL"


# ---------------------------------------------------------------------------
# send_signal — dry run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_returns_true(self, dry_run_notifier: TelegramNotifier, sample_signal: NotificationPayload) -> None:
        assert dry_run_notifier.send_signal(sample_signal) is True

    def test_dry_run_makes_no_http_calls(self, dry_run_notifier: TelegramNotifier, sample_signal: NotificationPayload) -> None:
        with patch("sentic_notifier.notifier.telegram.requests.post") as mock_post:
            dry_run_notifier.send_signal(sample_signal)
            mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# send_signal — live (mocked HTTP)
# ---------------------------------------------------------------------------

class TestSendSignal:
    def test_returns_true_on_success(self, notifier: TelegramNotifier, sample_signal: NotificationPayload) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status.return_value = None

        with patch("sentic_notifier.notifier.telegram.requests.post", return_value=mock_response):
            result = notifier.send_signal(sample_signal)

        assert result is True

    def test_returns_false_on_api_error(self, notifier: TelegramNotifier, sample_signal: NotificationPayload) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "description": "Bad Request"}
        mock_response.raise_for_status.return_value = None

        with patch("sentic_notifier.notifier.telegram.requests.post", return_value=mock_response):
            result = notifier.send_signal(sample_signal)

        assert result is False

    def test_returns_false_on_network_error(self, notifier: TelegramNotifier, sample_signal: NotificationPayload) -> None:
        import requests as req
        with patch("sentic_notifier.notifier.telegram.requests.post", side_effect=req.RequestException("timeout")):
            result = notifier.send_signal(sample_signal)

        assert result is False


# ---------------------------------------------------------------------------
# send_batch
# ---------------------------------------------------------------------------

class TestSendBatch:
    def test_returns_count_of_successes(self, notifier: TelegramNotifier, sample_signal: NotificationPayload) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status.return_value = None

        signals = [sample_signal, sample_signal]
        with patch("sentic_notifier.notifier.telegram.requests.post", return_value=mock_response):
            count = notifier.send_batch(signals)

        assert count == 2

    def test_partial_failure_counted(self, notifier: TelegramNotifier, sample_signal: NotificationPayload) -> None:
        ok_response = MagicMock()
        ok_response.json.return_value = {"ok": True}
        ok_response.raise_for_status.return_value = None

        fail_response = MagicMock()
        fail_response.json.return_value = {"ok": False, "description": "Flood control"}
        fail_response.raise_for_status.return_value = None

        signals = [sample_signal, sample_signal]
        with patch(
            "sentic_notifier.notifier.telegram.requests.post",
            side_effect=[ok_response, fail_response],
        ):
            count = notifier.send_batch(signals)

        assert count == 1

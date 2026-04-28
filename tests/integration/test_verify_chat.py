import os
import sys
from datetime import datetime
from pydantic import HttpUrl

sys.path.append(os.getcwd())

from sentic_notifier.notifier.telegram import TelegramNotifier
from sentic_notifier.models import NotificationPayload, SentimentLabel


from dotenv import load_dotenv

load_dotenv()


def test_verify_chat():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("❌ Missing environment variables!")
        return

    print(f"🚀 Initializing Notifier for Chat: {chat_id}")
    notifier = TelegramNotifier(bot_token=token, chat_id=chat_id)

    # Create a real Pydantic NotificationPayload object
    test_signal = NotificationPayload(
        ticker="TEST-OK",
        provider_sentiment=SentimentLabel.SOMEWHAT_BULLISH,
        headline="Integration Test: Sentic-Notifier is Live!",
        published=datetime.now(),
        url=HttpUrl("https://github.com/your-repo/sentic-notifier"),
        summary="Testing the connection between Pydantic models and Telegram API.",
        source="integration-test",
    )

    if notifier.send_signal(test_signal):
        print("✅ SUCCESS: Check your Telegram chat!")
    else:
        print("❌ FAILURE: Check console logs for API errors.")

if __name__ == "__main__":
    test_verify_chat()
# Sentic Notifier

Microservice responsible for consuming notification messages from the RabbitMQ `notifications` queue and dispatching them to configured channels. The current (and only) channel is Telegram.

---

## Role in the Pipeline

```
RabbitMQ: notifications queue
  → sentic-notifier (this service)
    → Telegram Bot API
```

`sentic-notifier` is a pure consumer. It never publishes back to the broker. All upstream services (`sentic-signal`, `sentic-analyst`, `sentic-quant`) publish `NotificationPayload` messages to the `notifications` queue.

---

## Message Contract — `NotificationPayload`

Defined in `sentic_notifier/models.py`. All publishers must conform to this schema.

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `UUID` | auto | Unique message ID for deduplication across restarts |
| `source` | `str` | no | Publishing service, e.g. `"sentic-signal"` |
| `ticker` | `str` | yes | Equity ticker, e.g. `"JNJ"` |
| `headline` | `str` | yes | Article headline |
| `url` | `HttpUrl` | yes | Canonical article URL |
| `published` | `datetime` | yes | UTC publication timestamp |
| `summary` | `str` | no | Short article summary |
| `provider_sentiment` | `SentimentLabel \| null` | no | Provider-supplied sentiment label |
| `sentic_sentiment` | `float \| null` | no | Sentic-computed score in `[-1.0, 1.0]` (Phase 2+) |

`SentimentLabel` values: `Bullish`, `Somewhat-Bullish`, `Neutral`, `Somewhat-Bearish`, `Bearish`.

**Versioning:** the model is intentionally minimal for Stage 1. New optional fields will be added as pipeline stages are introduced. Old messages always remain valid.

### Example payload (JSON)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "source": "sentic-signal",
  "ticker": "JNJ",
  "headline": "J&J reports stronger-than-expected Q1 earnings",
  "url": "https://example.com/jnj-q1-2026",
  "published": "2026-04-28T09:30:00Z",
  "summary": "Johnson & Johnson beat consensus EPS estimates by 4%.",
  "provider_sentiment": "Bullish",
  "sentic_sentiment": null
}
```

### Telegram output format

```
📡 *JNJ* | Bullish 🟢
🗞 J&J reports stronger-than-expected Q1 earnings
📅 2026-04-28 09:30 UTC
🔗 [Read Article](https://example.com/jnj-q1-2026)
```

---

## Architecture

```
sentic_notifier/
  models.py                  # NotificationPayload — the notifications queue contract
  main.py                    # Entrypoint: reads env, wires consumer + notifier
  consumer/
    rabbitmq_consumer.py     # aio-pika async consumer loop
  notifier/
    telegram.py              # TelegramNotifier — formats and dispatches signals
```

**Key design decisions:**

- **`aio-pika` (async)** — the consumer loop is I/O-bound (Telegram HTTP calls); async is the natural fit and will compose cleanly as more pipeline stages add concurrent consumers.
- **`passive=True` queue declaration** — the consumer never creates infrastructure. The queue is owned by the RabbitMQ Messaging Topology Operator (`sentic-infra`).
- **`prefetch_count=1`** — one in-flight message per consumer instance; safe for Telegram's rate limits.
- **Ack-after-dispatch** — messages are always acked after a dispatch attempt. Telegram API errors are logged but not nacked, since an immediate retry would hit the same error. Dead-letter / retry strategy is handled at the RabbitMQ topology level.
- **`connect_robust`** — handles transient broker restarts transparently without crashing the process.

---

## Configuration

All configuration is via environment variables. No config files.

| Variable | Required | Default | Description |
|---|---|---|---|
| `AMQP_URL` | yes | — | Full AMQP URL, e.g. `amqp://user:pass@rabbitmq:5672/vhost` |
| `NOTIFICATIONS_QUEUE` | no | `notifications` | Queue name to consume from |
| `TELEGRAM_BOT_TOKEN` | yes | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | yes | — | Target chat or channel ID |
| `DRY_RUN` | no | `false` | When `true`, logs messages instead of sending to Telegram |

---

## Development

### Install dependencies

```bash
poetry install
```

### Run unit tests

```bash
poetry run pytest tests/unit/
```

### Run integration test (sends a real Telegram message)

Requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in a `.env` file or the shell environment.

```bash
poetry run pytest tests/integration/
```

### Run locally (dry run)

```bash
AMQP_URL=amqp://guest:guest@localhost:5672/ \
TELEGRAM_BOT_TOKEN=<token> \
TELEGRAM_CHAT_ID=<chat_id> \
DRY_RUN=true \
poetry run python -m sentic_notifier.main
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `aio-pika` | Async RabbitMQ consumer (AMQP 0-9-1) |
| `pydantic` | Message schema validation |
| `requests` | Telegram Bot API HTTP calls |

---

## Future Evolution

The `NotificationPayload` contract is designed to grow incrementally:

- **Stage 4 (sentic-analyst):** adds `sentic_sentiment`, `red_team_critique`, `blue_team_critique`, `fused_score` as new optional fields — old consumers remain valid.
- **Stage 5 (sentic-quant):** may introduce a `notification_type` discriminator once quant summaries have a meaningfully different shape from article alerts.
- **Additional channels:** Slack, email, webhooks — implement as new notifier classes alongside `TelegramNotifier` and route by configuration.

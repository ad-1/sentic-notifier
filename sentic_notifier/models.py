"""Pydantic data contracts for the Sentic Notifier service.

NotificationPayload is the canonical message contract on the `notifications`
RabbitMQ queue. All upstream services (sentic-signal, sentic-analyst,
sentic-quant) must publish to this schema.

The model is intentionally minimal for Stage 1. Fields will be added as new
pipeline stages are introduced — always with defaults so old messages remain
valid.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


class SentimentLabel(str, Enum):
    BULLISH = "Bullish"
    SOMEWHAT_BULLISH = "Somewhat-Bullish"
    NEUTRAL = "Neutral"
    SOMEWHAT_BEARISH = "Somewhat-Bearish"
    BEARISH = "Bearish"


class NewsItem(BaseModel):
    """A single news article normalised from any provider.

    Every ingestor — regardless of the underlying API or feed — must produce
    NewsItem objects that conform to this schema. This is the "Sentic Standard"
    that enforces provider-agnostic behaviour throughout the pipeline.
    """

    ticker: str = Field(..., description="The equity ticker this article relates to.")
    headline: str = Field(..., description="Article title / headline.")
    url: HttpUrl = Field(..., description="Canonical URL of the article.")
    summary: str = Field(default="", description="Short article summary.")
    published: datetime = Field(..., description="UTC publication timestamp.")
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ticker relevance score (0–1). Provider-supplied or heuristically computed.",
    )
    source_provider: str = Field(
        default="",
        description="Identifies the origin provider (e.g. 'alpha_vantage', 'yahoo_rss').",
    )
    provider_sentiment: SentimentLabel | None = Field(
        default=None,
        description=(
            "Sentiment label supplied by the provider. Not all providers include this "
            "(e.g. Yahoo RSS returns None). The analyst worker adds sentic_sentiment for all items."
        ),
    )
    sentic_sentiment: float | None = Field(
        default=None,
        description=(
            "Sentic-computed sentiment score in [-1.0, 1.0]. "
            "Populated by the analyst worker (Phase 2). None until then."
        ),
    )


class NotificationPayload(BaseModel):
    """The canonical message contract for the `notifications` RabbitMQ queue.

    Published by sentic-signal (Stage 1), sentic-analyst (Stage 4), and
    sentic-quant (Stage 5). Consumed exclusively by sentic-notifier.

    id and source are used for idempotency and audit tracing respectively.
    All fields beyond the core set are optional so the contract degrades
    gracefully across pipeline stages.
    """

    id: UUID = Field(
        default_factory=uuid4,
        description="Unique message ID. Used for deduplication across service restarts.",
    )
    source: str = Field(
        default="",
        description="Service that published this notification, e.g. 'sentic-signal'.",
    )
    ticker: str
    headline: str
    url: HttpUrl
    published: datetime
    summary: str = ""
    provider_sentiment: SentimentLabel | None = None
    sentic_sentiment: float | None = None

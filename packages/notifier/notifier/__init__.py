"""IIC notifier package — WeCom bot + WeCom app + Server酱 + ntfy + SMTP adapters (workflow 20)."""

from .adapters import (
    Adapter,
    AdapterDown,
    AdapterRateLimit,
    AdapterRejected,
    NtfyAdapter,
    ServerChanAdapter,
    SmtpAdapter,
    WeComAppAdapter,
    WeComBotAdapter,
)
from .markdown_normalizer import clean
from .ratelimit import RateLimiter
from .redelivery import (
    TTL_BY_SEVERITY,
    InMemoryRedeliveryQueue,
    QueuedMessage,
    RedeliveryDrainer,
    RedeliveryQueue,
    RedisRedeliveryQueue,
    deferred_event_payload,
    delivered_event_payload,
    notify_with_redelivery,
)
from .router import NotifyExhausted, Router, build_router, severity_to_channels
from .types import (
    AdapterAttempt,
    ChannelHint,
    Notification,
    NotifyResult,
    Severity,
)

__version__ = "0.1.0"
__all__ = [
    "Adapter",
    "AdapterAttempt",
    "AdapterDown",
    "AdapterRateLimit",
    "AdapterRejected",
    "ChannelHint",
    "InMemoryRedeliveryQueue",
    "NotifyExhausted",
    "NotifyResult",
    "Notification",
    "NtfyAdapter",
    "QueuedMessage",
    "RateLimiter",
    "RedeliveryDrainer",
    "RedeliveryQueue",
    "RedisRedeliveryQueue",
    "Router",
    "ServerChanAdapter",
    "Severity",
    "SmtpAdapter",
    "TTL_BY_SEVERITY",
    "WeComAppAdapter",
    "WeComBotAdapter",
    "build_router",
    "clean",
    "deferred_event_payload",
    "delivered_event_payload",
    "notify_with_redelivery",
    "severity_to_channels",
]

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
    "NotifyExhausted",
    "NotifyResult",
    "Notification",
    "NtfyAdapter",
    "RateLimiter",
    "Router",
    "ServerChanAdapter",
    "Severity",
    "SmtpAdapter",
    "WeComAppAdapter",
    "WeComBotAdapter",
    "build_router",
    "clean",
    "severity_to_channels",
]

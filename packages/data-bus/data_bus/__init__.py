"""IIC data_bus package — NATS JetStream adapter + topic registry (workflow 05)."""

from .client import connect, jetstream
from .exceptions import DataBusError, HandlerError, InvalidSubject, StreamNotFound
from .publish import publish
from .streams import ensure_kv_buckets, ensure_streams
from .subjects import (
    ADVICE_FUNDAMENTAL,
    ADVICE_QUANT,
    BACKTEST_DAILY,
    BACKTEST_FILL,
    BACKTEST_LEADERBOARD,
    INTEL_BRIEF,
    INTEL_DASHBOARD,
    INTEL_DIGEST,
    KV_BUCKETS,
    OPS_ALERT,
    OPS_HEARTBEAT,
    SECRETARY_NOTIFY,
    STREAMS,
    advice_persona,
    assert_valid_subject,
    stream_for,
)
from .subscribe import Subscription, subscribe

__version__ = "0.1.0"
__all__ = [
    # client
    "connect",
    "jetstream",
    # publish/subscribe
    "publish",
    "subscribe",
    "Subscription",
    # streams + subjects
    "ensure_streams",
    "ensure_kv_buckets",
    "STREAMS",
    "KV_BUCKETS",
    "advice_persona",
    "assert_valid_subject",
    "stream_for",
    # subject constants
    "INTEL_DIGEST",
    "INTEL_DASHBOARD",
    "INTEL_BRIEF",
    "ADVICE_FUNDAMENTAL",
    "ADVICE_QUANT",
    "BACKTEST_FILL",
    "BACKTEST_DAILY",
    "BACKTEST_LEADERBOARD",
    "SECRETARY_NOTIFY",
    "OPS_HEARTBEAT",
    "OPS_ALERT",
    # errors
    "DataBusError",
    "InvalidSubject",
    "StreamNotFound",
    "HandlerError",
]

"""Public types for the notifier package (workflow 20 §5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    ALERT = "alert"
    CRITICAL = "critical"


class ChannelHint(StrEnum):
    BRIEFS = "briefs"
    ALERTS = "alerts"
    FILLS = "fills"
    CHAT = "chat"


Language = Literal["en", "zh"]


@dataclass(slots=True)
class Notification:
    """Inbound message — mirrors `secretary.notify.v1` (workflow 05 §4.6)."""

    severity: Severity
    channel_hint: ChannelHint
    markdown: str
    language: Language = "en"
    mentioned_list: list[str] | None = None
    target_user: str | None = None  # for wecom_app


@dataclass(slots=True)
class AdapterAttempt:
    name: str
    succeeded: bool
    latency_ms: int = 0
    error: str | None = None


@dataclass(slots=True)
class NotifyResult:
    """What `notify(n)` returns. Records every adapter that was tried."""

    severity: Severity
    channel_hint: ChannelHint
    attempts: list[AdapterAttempt] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        return any(a.succeeded for a in self.attempts)

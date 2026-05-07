"""Trigger shape — every entry point (cron, NATS, HTTP) funnels into one Trigger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

TriggerKind = Literal["cron", "event", "http", "request"]


@dataclass(frozen=True, slots=True)
class Trigger:
    kind: TriggerKind
    name: str  # e.g., "cron:morning_brief", "event:intel.digest.v1", "http:morning_brief"
    fired_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    force: bool = False  # bypass idempotency cache (workflow 06 §9)

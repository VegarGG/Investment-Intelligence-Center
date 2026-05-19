"""NATS subjects the orchestrator listens to (workflow 06 §6.1)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING

import orjson

from .types import Trigger

if TYPE_CHECKING:
    from nats.aio.msg import Msg

log = logging.getLogger(__name__)

ORCH_SUBSCRIPTIONS = (
    ("intel.digest.v1", "orchestrator.intel_digest"),
    # P2.11 — wake the trading room / event-triage gate on high-impact events.
    ("intel.event.high_impact.v1", "orchestrator.intel_high_impact"),
    # P5.5 — treat geo cluster crossings as high-impact events for routing.
    ("intel.event.geo_cluster.v1", "orchestrator.intel_geo_cluster"),
    ("backtest.fill.v1", "orchestrator.backtest_fill"),
    ("ops.alert.v1", "orchestrator.ops_alert"),
)


def make_handler(
    subject: str,
    on_trigger: Callable[[Trigger], Awaitable[None]],
) -> Callable[[Msg], Awaitable[None]]:
    async def handler(msg: Msg) -> None:
        try:
            payload = orjson.loads(msg.data) if msg.data else {}
        except orjson.JSONDecodeError:
            log.warning("subject=%s payload not JSON; size=%d bytes", subject, len(msg.data or b""))
            payload = {"_raw": (msg.data or b"").decode(errors="replace")}
        await on_trigger(
            Trigger(
                kind="event",
                name=f"event:{subject}",
                fired_at=datetime.now(),
                payload=payload,
            )
        )

    return handler

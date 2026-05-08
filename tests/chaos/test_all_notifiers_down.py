"""v2.5 T1.4 chaos acceptance — kill every notifier adapter, brief still ships.

Plan §T1.4 acceptance: kill all four notifier adapters mid-fanout, verify
the message redelivers within TTL once any adapter recovers; the brief
still appears in the dashboard regardless.

This synthetic test stands in for the production chaos drill — a real
drill would do the same thing against `docker compose down notifier_*`.
"""

from __future__ import annotations

import pytest
from notifier.adapters.base import AdapterDown
from notifier.ratelimit import RateLimiter
from notifier.redelivery import (
    InMemoryRedeliveryQueue,
    RedeliveryDrainer,
    notify_with_redelivery,
)
from notifier.router import build_router
from notifier.types import ChannelHint, Notification, Severity


class _FlaggableAdapter:
    """Adapter that fails / succeeds based on the `fail` flag."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.fail = True
        self.calls = 0

    async def send(self, _notification: Notification) -> None:
        self.calls += 1
        if self.fail:
            raise AdapterDown(f"{self.name} chaos-down")


@pytest.mark.asyncio
async def test_chaos_all_notifiers_down_recovery_round_trip():
    """1) all 4 down → defer; 2) recover one → drain; brief always available."""

    adapters = [
        _FlaggableAdapter("wecom_bot"),
        _FlaggableAdapter("serverchan"),
        _FlaggableAdapter("ntfy"),
        _FlaggableAdapter("smtp"),
    ]
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()

    # The brief markdown — proxy for "the brief in MinIO" (we don't run MinIO
    # in this synthetic test; the markdown body IS the artifact).
    brief_md = "## Morning brief\n- foo"

    # Phase 1 — all 4 adapters down. notify_with_redelivery suppresses
    # NotifyExhausted and queues the message.
    deferred_calls: list[str] = []

    async def on_deferred(msg):
        deferred_calls.append(msg.notification_id)

    out = await notify_with_redelivery(
        router,
        Notification(severity=Severity.ALERT, channel_hint=ChannelHint.BRIEFS, markdown=brief_md),
        queue,
        notification_id="brief-2026-05-08",
        trace_id="trace-001",
        on_deferred=on_deferred,
    )
    assert out is None, "expected deferral when all adapters down"
    assert await queue.size() == 1
    assert deferred_calls == ["brief-2026-05-08"]

    # Phase 2 — the brief is still readable (we hold its markdown body).
    # In production, the dashboard's reconciliation page would pull from
    # MinIO. Here we just assert the message body wasn't lost.
    pending = await queue.list_pending()
    assert pending[0].notification.markdown == brief_md

    # Phase 3 — recover serverchan (an ALERT fallback).
    adapters[1].fail = False
    drainer = RedeliveryDrainer(router=router, queue=queue, interval_s=0.01)
    delivered = await drainer.drain_once()
    assert delivered == 1
    assert await queue.size() == 0


@pytest.mark.asyncio
async def test_chaos_critical_severity_uses_extended_ttl():
    """CRITICAL gets 1 h TTL; INFO gets 24 h. Verifies severity-based TTL plumbing."""
    adapters = [
        _FlaggableAdapter("wecom_bot"),
        _FlaggableAdapter("serverchan"),
        _FlaggableAdapter("ntfy"),
        _FlaggableAdapter("smtp"),
    ]
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()

    await notify_with_redelivery(
        router,
        Notification(severity=Severity.CRITICAL, channel_hint=ChannelHint.ALERTS, markdown="!!"),
        queue,
        notification_id="crit-1",
    )
    await notify_with_redelivery(
        router,
        Notification(severity=Severity.INFO, channel_hint=ChannelHint.BRIEFS, markdown="ok"),
        queue,
        notification_id="info-1",
    )

    pending = {m.notification_id: m for m in await queue.list_pending()}
    crit_ttl = pending["crit-1"].expires_at - pending["crit-1"].enqueued_at
    info_ttl = pending["info-1"].expires_at - pending["info-1"].enqueued_at
    assert crit_ttl == pytest.approx(3600, abs=1)
    assert info_ttl == pytest.approx(24 * 3600, abs=1)

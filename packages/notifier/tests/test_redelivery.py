"""v2.5 T1.4 — durable redelivery queue acceptance.

Plan §T1.4: kill all four adapters mid-fanout, verify the message
redelivers within TTL once any adapter recovers; the brief still
appears in the dashboard regardless.
"""

from __future__ import annotations

import asyncio

import pytest
from notifier.adapters.base import AdapterDown
from notifier.ratelimit import RateLimiter
from notifier.redelivery import (
    InMemoryRedeliveryQueue,
    QueuedMessage,
    RedeliveryDrainer,
    notify_with_redelivery,
)
from notifier.router import NotifyExhausted, build_router
from notifier.types import ChannelHint, Notification, Severity


class _Recording:
    """Adapter stub that can be flipped between up/down at runtime."""

    def __init__(self, name: str, *, fail: bool = True) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    async def send(self, _notification: Notification) -> None:
        self.calls += 1
        if self.fail:
            raise AdapterDown(f"{self.name} down")


def _note(severity: Severity = Severity.ALERT) -> Notification:
    return Notification(
        severity=severity, channel_hint=ChannelHint.BRIEFS, markdown="hello"
    )


def _all_adapters(*, fail: bool):
    return [
        _Recording("wecom_bot", fail=fail),
        _Recording("serverchan", fail=fail),
        _Recording("ntfy", fail=fail),
        _Recording("smtp", fail=fail),
    ]


@pytest.mark.asyncio
async def test_redelivery_queue_enqueues_on_exhausted():
    """All adapters down → message lands in queue, exception suppressed."""
    adapters = _all_adapters(fail=True)
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()

    deferred_seen: list[QueuedMessage] = []

    async def on_deferred(msg):
        deferred_seen.append(msg)

    out = await notify_with_redelivery(
        router,
        _note(),
        queue,
        trace_id="trace-xyz",
        notification_id="msg-1",
        on_deferred=on_deferred,
    )
    assert out is None  # deferred — not raised
    assert await queue.size() == 1
    assert deferred_seen[0].notification_id == "msg-1"
    assert deferred_seen[0].trace_id == "trace-xyz"


@pytest.mark.asyncio
async def test_drainer_redelivers_when_any_adapter_recovers():
    """All adapters down → queued. Recover one adapter, drain → delivered."""
    adapters = _all_adapters(fail=True)
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()

    await notify_with_redelivery(router, _note(), queue, notification_id="msg-2")
    assert await queue.size() == 1

    # Recover one adapter — wecom_bot is the primary for ALERT severity.
    adapters[0].fail = False

    drainer = RedeliveryDrainer(router=router, queue=queue, interval_s=0.01)
    delivered = await drainer.drain_once()
    assert delivered == 1
    assert await queue.size() == 0


@pytest.mark.asyncio
async def test_drainer_keeps_message_when_all_still_down():
    adapters = _all_adapters(fail=True)
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()

    await notify_with_redelivery(router, _note(), queue, notification_id="msg-3")
    drainer = RedeliveryDrainer(router=router, queue=queue, interval_s=0.01)
    delivered = await drainer.drain_once()
    assert delivered == 0
    assert await queue.size() == 1
    pending = await queue.list_pending()
    assert pending[0].attempts == 1
    assert pending[0].last_error is not None


@pytest.mark.asyncio
async def test_severity_ttl_table_complete():
    from notifier.redelivery import TTL_BY_SEVERITY

    for sev in Severity:
        assert sev in TTL_BY_SEVERITY
    # CRITICAL = 1 h ; INFO = 24 h ; ALERT = 6 h
    assert TTL_BY_SEVERITY[Severity.CRITICAL] == 3600
    assert TTL_BY_SEVERITY[Severity.ALERT] == 6 * 3600
    assert TTL_BY_SEVERITY[Severity.INFO] == 24 * 3600


@pytest.mark.asyncio
async def test_redelivery_returns_normal_result_on_success():
    """When primary delivers, no queue write; result returned."""
    adapters = _all_adapters(fail=False)
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()
    out = await notify_with_redelivery(router, _note(), queue, notification_id="msg-4")
    assert out is not None
    assert out.succeeded
    assert await queue.size() == 0


@pytest.mark.asyncio
async def test_drainer_lifecycle_start_stop():
    adapters = _all_adapters(fail=True)
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()
    drainer = RedeliveryDrainer(router=router, queue=queue, interval_s=0.05)
    drainer.start()
    await asyncio.sleep(0.01)
    await drainer.stop()
    # Idempotent stop.
    await drainer.stop()


@pytest.mark.asyncio
async def test_full_chaos_recovery_round_trip():
    """Plan §T1.4 acceptance: all four down, then any one recovers, message drains."""
    adapters = _all_adapters(fail=True)
    router = build_router(adapters, rate_limiter=RateLimiter(limits={}))
    queue = InMemoryRedeliveryQueue()
    drainer = RedeliveryDrainer(router=router, queue=queue, interval_s=0.01)

    # Step 1 — all down, message deferred.
    await notify_with_redelivery(router, _note(Severity.ALERT), queue, notification_id="m-A")
    await notify_with_redelivery(router, _note(Severity.ALERT), queue, notification_id="m-B")
    assert await queue.size() == 2

    # Step 2 — recover serverchan (fallback for ALERT).
    adapters[1].fail = False  # serverchan
    delivered = await drainer.drain_once()
    assert delivered == 2
    assert await queue.size() == 0

"""Durable redelivery queue for the notifier (v2.5 T1.4).

When `Router.notify()` raises `NotifyExhausted`, the message is enqueued
here with a severity-dependent TTL. A 60-second background drain task
re-attempts redelivery against any adapter that has come back online.

Two backends:
- `InMemoryRedeliveryQueue` — used by chaos tests + the dashboard's
  reconciliation page in development.
- `RedisRedeliveryQueue` — production, durable across orchestrator restarts.

CRITICAL severity also fires a Tailscale-only ntfy push to Ziwei's phone
via env-configured `NTFY_TAILSCALE_TOPIC` so the principal sees the
deferred state immediately.

Plan §T1.4 acceptance: kill all four notifier adapters mid-fanout, verify
the message redelivers within TTL once any adapter recovers; the brief
still appears in the dashboard regardless (because compose/deliver is
split — see `Router.compose_only()` / `notify_with_redelivery()`).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .router import NotifyExhausted, Router
from .types import Notification, NotifyResult, Severity

log = logging.getLogger(__name__)


# Severity → seconds until the queued message gives up.
TTL_BY_SEVERITY: dict[Severity, int] = {
    Severity.CRITICAL: 60 * 60,        # 1 h
    Severity.ALERT: 60 * 60 * 6,       # 6 h
    Severity.WARN: 60 * 60 * 12,       # 12 h
    Severity.INFO: 60 * 60 * 24,       # 24 h
}

DEFAULT_DRAIN_INTERVAL_S = 60.0


@dataclass(slots=True)
class QueuedMessage:
    notification_id: str
    notification: Notification
    enqueued_at: float                 # monotonic seconds
    expires_at: float                  # monotonic seconds
    trace_id: str | None = None
    attempts: int = 0
    last_error: str | None = None


class RedeliveryQueue(Protocol):
    async def enqueue(self, msg: QueuedMessage) -> None: ...
    async def list_pending(self) -> list[QueuedMessage]: ...
    async def remove(self, notification_id: str) -> None: ...
    async def update_attempt(self, notification_id: str, error: str) -> None: ...
    async def size(self) -> int: ...


class InMemoryRedeliveryQueue:
    """Process-local queue. Deterministic ordering for tests."""

    def __init__(self) -> None:
        self._items: dict[str, QueuedMessage] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, msg: QueuedMessage) -> None:
        async with self._lock:
            self._items[msg.notification_id] = msg

    async def list_pending(self) -> list[QueuedMessage]:
        async with self._lock:
            now = time.monotonic()
            return [m for m in self._items.values() if m.expires_at > now]

    async def remove(self, notification_id: str) -> None:
        async with self._lock:
            self._items.pop(notification_id, None)

    async def update_attempt(self, notification_id: str, error: str) -> None:
        async with self._lock:
            msg = self._items.get(notification_id)
            if msg is None:
                return
            msg.attempts += 1
            msg.last_error = error

    async def size(self) -> int:
        async with self._lock:
            return len(self._items)


class RedisRedeliveryQueue:
    """Production queue. Stores serialized payloads under
    ``notifier:redelivery:<notification_id>`` with severity TTL.
    """

    PREFIX = "notifier:redelivery:"

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    async def enqueue(self, msg: QueuedMessage) -> None:
        import orjson
        payload = orjson.dumps(_serialize(msg))
        ttl = max(int(msg.expires_at - time.monotonic()), 1)
        await self._redis.set(f"{self.PREFIX}{msg.notification_id}", payload, ex=ttl)

    async def list_pending(self) -> list[QueuedMessage]:
        import orjson
        pending: list[QueuedMessage] = []
        async for key in self._redis.scan_iter(match=f"{self.PREFIX}*"):
            raw = await self._redis.get(key)
            if not raw:
                continue
            try:
                d = orjson.loads(raw)
                pending.append(_deserialize(d))
            except Exception:
                continue
        return pending

    async def remove(self, notification_id: str) -> None:
        await self._redis.delete(f"{self.PREFIX}{notification_id}")

    async def update_attempt(self, notification_id: str, error: str) -> None:
        import orjson
        key = f"{self.PREFIX}{notification_id}"
        raw = await self._redis.get(key)
        if not raw:
            return
        d = orjson.loads(raw)
        d["attempts"] = d.get("attempts", 0) + 1
        d["last_error"] = error
        ttl = await self._redis.ttl(key) or 60
        await self._redis.set(key, orjson.dumps(d), ex=max(ttl, 1))

    async def size(self) -> int:
        n = 0
        async for _ in self._redis.scan_iter(match=f"{self.PREFIX}*"):
            n += 1
        return n


def _serialize(msg: QueuedMessage) -> dict[str, Any]:
    n = msg.notification
    return {
        "notification_id": msg.notification_id,
        "trace_id": msg.trace_id,
        "enqueued_at": msg.enqueued_at,
        "expires_at": msg.expires_at,
        "attempts": msg.attempts,
        "last_error": msg.last_error,
        "notification": {
            "severity": n.severity.value,
            "channel_hint": n.channel_hint.value,
            "markdown": n.markdown,
            "language": n.language,
            "mentioned_list": n.mentioned_list,
            "target_user": n.target_user,
        },
    }


def _deserialize(d: dict[str, Any]) -> QueuedMessage:
    from .types import ChannelHint

    n = d["notification"]
    return QueuedMessage(
        notification_id=d["notification_id"],
        notification=Notification(
            severity=Severity(n["severity"]),
            channel_hint=ChannelHint(n["channel_hint"]),
            markdown=n["markdown"],
            language=n.get("language", "en"),
            mentioned_list=n.get("mentioned_list"),
            target_user=n.get("target_user"),
        ),
        enqueued_at=float(d["enqueued_at"]),
        expires_at=float(d["expires_at"]),
        trace_id=d.get("trace_id"),
        attempts=int(d.get("attempts", 0)),
        last_error=d.get("last_error"),
    )


async def notify_with_redelivery(
    router: Router,
    notification: Notification,
    queue: RedeliveryQueue,
    *,
    trace_id: str | None = None,
    notification_id: str | None = None,
    on_deferred: Any = None,
) -> NotifyResult | None:
    """Send a notification; if all adapters are down, enqueue for redelivery.

    Returns the NotifyResult on success, or None when the message was
    deferred to the redelivery queue. Raising is suppressed because the
    DAG node `n_deliver_brief` must never fail (plan §T1.4b).
    """

    try:
        return await router.notify(notification)
    except NotifyExhausted as exc:
        nid = notification_id or str(uuid.uuid4())
        ttl_s = TTL_BY_SEVERITY.get(notification.severity, 6 * 3600)
        msg = QueuedMessage(
            notification_id=nid,
            notification=notification,
            enqueued_at=time.monotonic(),
            expires_at=time.monotonic() + ttl_s,
            trace_id=trace_id,
            last_error=str(exc),
        )
        await queue.enqueue(msg)
        log.warning(
            "notify deferred severity=%s ttl_s=%d trace_id=%s",
            notification.severity.value,
            ttl_s,
            trace_id,
        )
        if on_deferred is not None:
            with contextlib.suppress(Exception):
                await on_deferred(msg)
        if notification.severity is Severity.CRITICAL:
            await _critical_tailscale_push(notification)
        return None


async def _critical_tailscale_push(notification: Notification) -> None:
    """Last-resort ntfy-on-Tailscale push when all primary adapters are down."""
    topic = os.environ.get("NTFY_TAILSCALE_TOPIC")
    if not topic:
        return
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://ntfy.sh/{topic}",
                content=notification.markdown.encode("utf-8"),
                headers={"Title": "IIC CRITICAL — primaries down", "Priority": "max"},
            )
    except Exception:
        log.warning("tailscale ntfy fallback failed", exc_info=True)


@dataclass(slots=True)
class RedeliveryDrainer:
    """Background task that retries messages on every interval."""

    router: Router
    queue: RedeliveryQueue
    interval_s: float = DEFAULT_DRAIN_INTERVAL_S
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _stopping: asyncio.Event = field(default_factory=asyncio.Event, init=False)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def drain_once(self) -> int:
        """Attempt redelivery of every pending message exactly once.

        Returns the number of messages that successfully delivered this pass.
        """
        delivered = 0
        for msg in await self.queue.list_pending():
            try:
                await self.router.notify(msg.notification)
            except NotifyExhausted as exc:
                await self.queue.update_attempt(msg.notification_id, str(exc))
                continue
            await self.queue.remove(msg.notification_id)
            delivered += 1
            log.info(
                "redelivered notification id=%s attempts=%d",
                msg.notification_id,
                msg.attempts + 1,
            )
        return delivered

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.drain_once()
            except Exception:
                log.exception("redelivery drain raised")
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval_s)
            except TimeoutError:
                continue


def deferred_event_payload(msg: QueuedMessage) -> dict[str, Any]:
    """Payload for `notify.deferred.v1` NATS event."""
    return {
        "notification_id": msg.notification_id,
        "trace_id": msg.trace_id,
        "severity": msg.notification.severity.value,
        "channel_hint": msg.notification.channel_hint.value,
        "enqueued_at_iso": datetime.now(UTC).isoformat(),
        "ttl_remaining_s": int(max(msg.expires_at - time.monotonic(), 0)),
        "last_error": msg.last_error,
    }


def delivered_event_payload(msg: QueuedMessage) -> dict[str, Any]:
    """Payload for `notify.delivered.v1` NATS event."""
    return {
        "notification_id": msg.notification_id,
        "trace_id": msg.trace_id,
        "severity": msg.notification.severity.value,
        "delivered_at_iso": datetime.now(UTC).isoformat(),
        "attempts": msg.attempts + 1,
    }

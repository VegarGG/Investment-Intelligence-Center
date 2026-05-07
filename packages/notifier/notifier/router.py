"""Notifier router (workflow 20 §6 + §9).

Severity → channel mapping is GROUND TRUTH from §6. `notify(n)` runs the
primary first, cascades through fallbacks on `AdapterDown`/`AdapterRateLimit`.
For `severity=critical` the fanout runs in parallel.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from .adapters.base import Adapter, AdapterDown, AdapterRateLimit, AdapterRejected
from .ratelimit import RateLimiter
from .types import AdapterAttempt, ChannelHint, Notification, NotifyResult, Severity

log = logging.getLogger(__name__)


class NotifyExhausted(Exception):
    """All adapters in the chain failed."""


@dataclass(slots=True)
class Plan:
    """Which adapter goes first, which fall back, and whether to fan out in parallel."""

    primary: list[Adapter]
    fallbacks: list[Adapter]
    parallel: bool = False


def severity_to_channels(
    severity: Severity,
    *,
    by_name: dict[str, Adapter],
) -> Plan:
    """GROUND TRUTH from §6 routing table."""
    wecom = by_name.get("wecom_bot")
    sc = by_name.get("serverchan")
    ntfy = by_name.get("ntfy")
    smtp = by_name.get("smtp")

    if severity == Severity.CRITICAL:
        primaries = [a for a in (wecom, sc, ntfy, smtp) if a is not None]
        return Plan(primary=primaries, fallbacks=[], parallel=True)
    if severity == Severity.ALERT:
        primaries = [a for a in (wecom, sc) if a is not None]
        fallbacks = [a for a in (ntfy, smtp) if a is not None]
        return Plan(primary=primaries, fallbacks=fallbacks)
    # info / warn — single primary plus the standard cascade
    fallbacks = [a for a in (sc, ntfy, smtp) if a is not None]
    if wecom is None:
        return Plan(primary=fallbacks[:1], fallbacks=fallbacks[1:])
    return Plan(primary=[wecom], fallbacks=fallbacks)


@dataclass(slots=True)
class Router:
    adapters: dict[str, Adapter]
    rate_limiter: RateLimiter

    async def notify(self, notification: Notification) -> NotifyResult:
        result = NotifyResult(
            severity=notification.severity, channel_hint=notification.channel_hint
        )
        plan = severity_to_channels(notification.severity, by_name=self.adapters)

        if plan.parallel:
            await self._run_parallel(plan.primary, notification, result)
        else:
            await self._run_cascade(plan.primary + plan.fallbacks, notification, result)

        result.finished_at = datetime.now(UTC)
        if not result.succeeded:
            raise NotifyExhausted(f"all adapters failed for severity={notification.severity.value}")
        return result

    async def _run_cascade(
        self, chain: list[Adapter], notification: Notification, result: NotifyResult
    ) -> None:
        for adapter in chain:
            attempt = await self._try_adapter(adapter, notification)
            result.attempts.append(attempt)
            if attempt.succeeded:
                return

    async def _run_parallel(
        self, chain: list[Adapter], notification: Notification, result: NotifyResult
    ) -> None:
        attempts = await asyncio.gather(*[self._try_adapter(a, notification) for a in chain])
        result.attempts.extend(attempts)

    async def _try_adapter(self, adapter: Adapter, notification: Notification) -> AdapterAttempt:
        rate_key = self._rate_key(adapter, notification.channel_hint)
        started = time.monotonic()
        try:
            await self.rate_limiter.acquire(rate_key)
            await adapter.send(notification)
        except AdapterRateLimit as exc:
            return _failure(adapter.name, started, f"rate_limit: {exc}")
        except AdapterDown as exc:
            return _failure(adapter.name, started, f"down: {exc}")
        except AdapterRejected as exc:
            log.warning("adapter %s rejected message: %s", adapter.name, exc)
            return _failure(adapter.name, started, f"rejected: {exc}")
        except Exception as exc:
            return _failure(adapter.name, started, f"error: {exc}")
        return AdapterAttempt(
            name=adapter.name,
            succeeded=True,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    @staticmethod
    def _rate_key(adapter: Adapter, hint: ChannelHint) -> str:
        if adapter.name == "wecom_bot":
            return f"wecom_bot:{hint.value}"
        return adapter.name


def build_router(adapters: Iterable[Adapter], rate_limiter: RateLimiter | None = None) -> Router:
    """Convenience factory — pass the adapters in and get a wired Router back."""
    by_name = {a.name: a for a in adapters}
    return Router(adapters=by_name, rate_limiter=rate_limiter or RateLimiter())


def _failure(name: str, started: float, error: str) -> AdapterAttempt:
    return AdapterAttempt(
        name=name,
        succeeded=False,
        latency_ms=int((time.monotonic() - started) * 1000),
        error=error,
    )

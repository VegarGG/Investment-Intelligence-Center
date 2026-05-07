"""Workflow 20 §9 — fallback cascade behavior."""

from __future__ import annotations

import pytest
from notifier.adapters.base import AdapterDown
from notifier.ratelimit import RateLimiter
from notifier.router import NotifyExhausted, build_router
from notifier.types import ChannelHint, Notification, Severity


class _RecordingAdapter:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self._fail = fail
        self.calls = 0

    async def send(self, _notification: Notification) -> None:
        self.calls += 1
        if self._fail:
            raise AdapterDown(f"{self.name} forced down")


def _note(severity: Severity = Severity.INFO) -> Notification:
    return Notification(
        severity=severity,
        channel_hint=ChannelHint.BRIEFS,
        markdown="hello",
    )


@pytest.mark.asyncio
async def test_info_succeeds_on_primary_no_cascade() -> None:
    wecom = _RecordingAdapter("wecom_bot")
    sc = _RecordingAdapter("serverchan")
    router = build_router([wecom, sc], rate_limiter=RateLimiter(limits={}))
    result = await router.notify(_note())
    assert result.succeeded
    assert wecom.calls == 1 and sc.calls == 0


@pytest.mark.asyncio
async def test_primary_failure_cascades_to_serverchan() -> None:
    wecom = _RecordingAdapter("wecom_bot", fail=True)
    sc = _RecordingAdapter("serverchan")
    router = build_router([wecom, sc], rate_limiter=RateLimiter(limits={}))
    result = await router.notify(_note())
    assert result.succeeded
    assert wecom.calls == 1 and sc.calls == 1
    assert any(a.error and "down" in a.error for a in result.attempts if a.name == "wecom_bot")


@pytest.mark.asyncio
async def test_all_adapters_failing_raises_exhausted() -> None:
    wecom = _RecordingAdapter("wecom_bot", fail=True)
    sc = _RecordingAdapter("serverchan", fail=True)
    ntfy = _RecordingAdapter("ntfy", fail=True)
    router = build_router([wecom, sc, ntfy], rate_limiter=RateLimiter(limits={}))
    with pytest.raises(NotifyExhausted):
        await router.notify(_note())


@pytest.mark.asyncio
async def test_critical_fans_all_in_parallel_one_success_enough() -> None:
    wecom = _RecordingAdapter("wecom_bot", fail=True)
    sc = _RecordingAdapter("serverchan", fail=True)
    ntfy = _RecordingAdapter("ntfy")
    smtp = _RecordingAdapter("smtp")
    router = build_router([wecom, sc, ntfy, smtp], rate_limiter=RateLimiter(limits={}))
    result = await router.notify(_note(Severity.CRITICAL))
    assert wecom.calls == sc.calls == ntfy.calls == smtp.calls == 1
    assert result.succeeded
    succeeded = [a.name for a in result.attempts if a.succeeded]
    assert set(succeeded) == {"ntfy", "smtp"}


@pytest.mark.asyncio
async def test_rate_limit_counts_as_failure_for_cascade() -> None:
    wecom = _RecordingAdapter("wecom_bot")
    sc = _RecordingAdapter("serverchan")
    rate = RateLimiter(limits={"wecom_bot:briefs": (1, 60.0)})
    router = build_router([wecom, sc], rate_limiter=rate)

    first = await router.notify(_note())
    assert first.succeeded
    second = await router.notify(_note())
    # Second call: wecom_bot rate-limited → cascade to serverchan.
    assert second.succeeded
    assert wecom.calls == 1
    assert sc.calls == 1

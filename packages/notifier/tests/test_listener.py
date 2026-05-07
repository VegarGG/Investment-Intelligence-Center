"""Workflow 20 §11.3 — bus listener glue."""

from __future__ import annotations

import pytest
from notifier.listener import from_event, handle
from notifier.ratelimit import RateLimiter
from notifier.router import build_router
from notifier.types import ChannelHint, Severity
from schema import SecretaryNotifyV1


def _event(severity: str = "info", hint: str = "briefs") -> SecretaryNotifyV1:
    return SecretaryNotifyV1(
        severity=severity,  # type: ignore[arg-type]
        channel_hint=hint,  # type: ignore[arg-type]
        markdown="hi",
    )


def test_from_event_translates_fields() -> None:
    n = from_event(_event(severity="alert", hint="alerts"))
    assert n.severity == Severity.ALERT
    assert n.channel_hint == ChannelHint.ALERTS


class _OkAdapter:
    name = "wecom_bot"

    async def send(self, _notification) -> None:
        return None


@pytest.mark.asyncio
async def test_handle_dispatches_via_router() -> None:
    router = build_router([_OkAdapter()], rate_limiter=RateLimiter(limits={}))
    seen = []

    async def on_done(result) -> None:
        seen.append(result)

    result = await handle(_event(), router=router, on_done=on_done)
    assert result.succeeded
    assert seen and seen[0] is result

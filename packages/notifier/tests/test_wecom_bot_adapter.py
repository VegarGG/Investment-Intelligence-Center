"""Workflow 20 §7.1 — WeCom bot adapter (httpx mock-transport)."""

from __future__ import annotations

import httpx
import pytest
from notifier.adapters.base import AdapterDown, AdapterRateLimit, AdapterRejected
from notifier.adapters.wecom_bot import WeComBotAdapter
from notifier.types import ChannelHint, Notification, Severity


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _note(channel: ChannelHint = ChannelHint.BRIEFS) -> Notification:
    return Notification(
        severity=Severity.INFO,
        channel_hint=channel,
        markdown="**hi** team",
        mentioned_list=["@all"],
    )


@pytest.mark.asyncio
async def test_send_to_briefs_succeeds() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content
        return httpx.Response(200, json={"errcode": 0})

    client = _client(handler)
    adapter = WeComBotAdapter(keys={"briefs": "test-key"}, client=client)
    await adapter.send(_note())
    assert "key=test-key" in captured["url"]  # type: ignore[operator]
    assert b"markdown" in captured["body"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_5xx_retried_then_raises_down() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    client = _client(handler)
    adapter = WeComBotAdapter(keys={"briefs": "k"}, client=client, max_retries=1)
    with pytest.raises(AdapterDown):
        await adapter.send(_note())
    assert calls["n"] == 2  # one + one retry


@pytest.mark.asyncio
async def test_429_raises_rate_limit() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    client = _client(handler)
    adapter = WeComBotAdapter(keys={"briefs": "k"}, client=client)
    with pytest.raises(AdapterRateLimit):
        await adapter.send(_note())


@pytest.mark.asyncio
async def test_unknown_channel_rejected() -> None:
    adapter = WeComBotAdapter(keys={"briefs": "k"}, client=_client(lambda _r: httpx.Response(200)))
    with pytest.raises(AdapterRejected):
        await adapter.send(_note(channel=ChannelHint.CHAT))


@pytest.mark.asyncio
async def test_missing_key_rejected() -> None:
    adapter = WeComBotAdapter(keys={}, client=_client(lambda _r: httpx.Response(200)))
    with pytest.raises(AdapterRejected):
        await adapter.send(_note())

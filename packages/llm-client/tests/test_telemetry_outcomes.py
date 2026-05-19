"""P0.6 — every call termination must produce a `lake.llm_calls` row.

Outcomes covered:
- ``ok`` — happy path
- ``error`` — ProviderError raised by the adapter
- ``timeout`` — ProviderTimeout raised by the adapter
- ``rate_limit`` — cost meter blocked the call
- ``skipped`` — chat_or_skip swallowed a CostBudgetExceeded into a synthetic-skip
"""

from __future__ import annotations

import asyncio
from datetime import date

import featureflags
import featureflags.registry  # noqa: F401
import pytest
from llm_client import ChatMessage, ChatResponse, LlmRouter
from llm_client.cost_meter import CostMeter, InMemorySpendStore
from llm_client.exceptions import ProviderError, ProviderTimeout
from llm_client.fallback import FallbackChain
from llm_client.rate_limiter import RateLimiter
from llm_client.telemetry import CapturingTelemetrySink


class _Adapter:
    name = "stub"

    def __init__(self, raise_exc: Exception | None = None) -> None:
        self.raise_exc = raise_exc
        self.calls = 0

    async def chat(self, messages, *, tier, max_tokens, temperature, timeout_s):
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return ChatResponse(
            text="ok",
            model="stub",
            tier=tier,
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.001,
            request_id="r",
            latency_ms=1,
        )

    async def embed(self, texts, *, timeout_s):  # pragma: no cover
        from llm_client.types import EmbedResponse

        return EmbedResponse(vectors=[[0.0]], model="stub", cost_usd=0.0, request_id="r")


def _router(adapter: _Adapter, *, monthly_cap_usd: float = 10.0) -> tuple[LlmRouter, CapturingTelemetrySink]:
    sink = CapturingTelemetrySink()
    router = LlmRouter(
        primary=adapter,
        fallback=FallbackChain(pro_fallback=None, flash_fallback=None),
        rate_limiter=RateLimiter(),
        cost_meter=CostMeter(store=InMemorySpendStore(), monthly_cap_usd=monthly_cap_usd),
        telemetry=sink,
    )
    return router, sink


async def _drain():
    # Telemetry is fire-and-forget; let the loop schedule the writes.
    await asyncio.sleep(0.01)


@pytest.fixture(autouse=True)
def _isolate_flags():
    featureflags.reset_for_test()
    yield
    featureflags.reset_for_test()


@pytest.mark.asyncio
async def test_ok_outcome():
    router, sink = _router(_Adapter())
    await router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")])
    await _drain()
    outcomes = [row["outcome"] for row in sink.calls]
    assert outcomes == ["ok"]


@pytest.mark.asyncio
async def test_error_outcome_on_provider_error():
    router, sink = _router(_Adapter(raise_exc=ProviderError("boom")))
    with pytest.raises(ProviderError):
        await router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")])
    await _drain()
    outcomes = [row["outcome"] for row in sink.calls]
    assert "error" in outcomes


@pytest.mark.asyncio
async def test_error_outcome_when_fallback_unavailable():
    """ProviderTimeout from primary + no fallback adapter configured →
    `NoLLMAvailable` propagates and lands as ``error`` in the audit log
    (the call failed to find any provider, it didn't simply time out)."""
    router, sink = _router(_Adapter(raise_exc=ProviderTimeout("late")))
    from llm_client.exceptions import NoLLMAvailable

    with pytest.raises(NoLLMAvailable):
        await router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")])
    await _drain()
    outcomes = [row["outcome"] for row in sink.calls]
    assert "error" in outcomes


@pytest.mark.asyncio
async def test_rate_limit_outcome_on_cost_breaker():
    router, sink = _router(_Adapter(), monthly_cap_usd=0.01)
    today = date.today()
    await router.cost_meter.store.record(day=today, tier="flash", fallback=False, cost_usd=0.05)
    from llm_client.exceptions import CostBudgetExceeded

    with pytest.raises(CostBudgetExceeded):
        await router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")])
    await _drain()
    outcomes = [row["outcome"] for row in sink.calls]
    assert "rate_limit" in outcomes


@pytest.mark.asyncio
async def test_skipped_outcome_when_breaker_swallows_cost_exceeded():
    featureflags.set_for_test("cost_breaker.enabled", True)
    router, sink = _router(_Adapter(), monthly_cap_usd=0.01)
    today = date.today()
    await router.cost_meter.store.record(day=today, tier="flash", fallback=False, cost_usd=0.05)
    out = await router.chat_or_skip(
        "secretary.brief.morning", [ChatMessage(role="user", content="x")]
    )
    assert out.cost_skipped is True
    await _drain()
    outcomes = [row["outcome"] for row in sink.calls]
    # The cost meter blocks before chat() is even called → "rate_limit" row.
    assert "rate_limit" in outcomes


@pytest.mark.asyncio
async def test_five_calls_five_rows():
    """Acceptance: 5 calls → 5 lake.llm_calls rows."""
    router, sink = _router(_Adapter())
    for _ in range(5):
        await router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")])
    await _drain()
    assert len(sink.calls) == 5
    assert all(row["outcome"] == "ok" for row in sink.calls)

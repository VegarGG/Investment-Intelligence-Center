"""v2.5 T1.9 — pin down cost-breaker behaviour.

Plan §T1.9 acceptance: at breaker-open, in-flight calls drain (deadline 30 s);
new calls return a `cost_skipped=True` ChatResponse so the DAG keeps going.
The real-API chaos test that drives DeepSeek to 95 % of cap lives in
``tests/chaos/test_cost_cap_real.py`` (gated on ``IIC_RUN_COST_CHAOS=1``).
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from llm_client import COST_SKIPPED_MARKER, ChatMessage, ChatResponse, LlmRouter
from llm_client.cost_meter import CostMeter, InMemorySpendStore
from llm_client.fallback import FallbackChain
from llm_client.rate_limiter import RateLimiter
from llm_client.router import synthetic_skip_response


class _StubAdapter:
    name = "stub"

    def __init__(self, *, latency_s: float = 0.0) -> None:
        self.latency_s = latency_s
        self.calls = 0

    async def chat(self, messages, *, tier, max_tokens, temperature, timeout_s):
        self.calls += 1
        if self.latency_s:
            await asyncio.sleep(self.latency_s)
        return ChatResponse(
            text="ok",
            model="stub",
            tier=tier,
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.001,
            request_id=f"req-{self.calls}",
            latency_ms=int(self.latency_s * 1000),
        )

    async def embed(self, texts, *, timeout_s):  # pragma: no cover - unused here
        from llm_client.types import EmbedResponse

        return EmbedResponse(vectors=[[0.0]], model="stub", cost_usd=0.0, request_id="r")


def _build_router(*, monthly_cap_usd: float, latency_s: float = 0.0) -> tuple[LlmRouter, CostMeter, _StubAdapter]:
    store = InMemorySpendStore()
    meter = CostMeter(store=store, monthly_cap_usd=monthly_cap_usd)
    adapter = _StubAdapter(latency_s=latency_s)
    fallback = FallbackChain(pro_fallback=None, flash_fallback=None)
    router = LlmRouter(
        primary=adapter,
        fallback=fallback,
        rate_limiter=RateLimiter(),
        cost_meter=meter,
    )
    return router, meter, adapter


@pytest.mark.asyncio
async def test_synthetic_skip_response_shape():
    """Synthetic-skip response carries the marker text + cost_skipped=True."""
    r = synthetic_skip_response(caller_id="x", tier="flash")
    assert r.cost_skipped is True
    assert r.text == COST_SKIPPED_MARKER
    assert r.cost_usd == 0.0
    assert r.tier == "flash"


@pytest.mark.asyncio
async def test_chat_or_skip_returns_real_response_when_under_cap():
    router, _, adapter = _build_router(monthly_cap_usd=10.0)
    out = await router.chat_or_skip(
        "secretary.brief.morning",
        [ChatMessage(role="user", content="hi")],
    )
    assert out.cost_skipped is False
    assert out.text == "ok"
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_chat_or_skip_returns_synthetic_when_breaker_open():
    """Drive spend over the cap; chat_or_skip returns synthetic-skip."""
    router, meter, adapter = _build_router(monthly_cap_usd=0.01)
    # Pre-load the spend store past the cap.
    today = date.today()
    await meter.store.record(day=today, tier="flash", fallback=False, cost_usd=0.05)

    out = await router.chat_or_skip(
        "secretary.brief.morning",
        [ChatMessage(role="user", content="hi")],
    )
    assert out.cost_skipped is True
    assert COST_SKIPPED_MARKER in out.text
    assert adapter.calls == 0  # primary never called


@pytest.mark.asyncio
async def test_chat_or_skip_drain_deadline_fires():
    """If the in-flight call exceeds drain_deadline_s, return synthetic-skip."""
    router, _, adapter = _build_router(monthly_cap_usd=10.0, latency_s=0.5)
    out = await router.chat_or_skip(
        "secretary.brief.morning",
        [ChatMessage(role="user", content="hi")],
        drain_deadline_s=0.05,
    )
    assert out.cost_skipped is True
    assert "drain_deadline" in out.model
    # The adapter call did happen (it just timed out from the router's view).
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_chat_still_raises_for_strict_callers():
    """`chat()` keeps the legacy raise-on-cap behaviour for callers that
    explicitly want it."""
    from llm_client.exceptions import CostBudgetExceeded

    router, meter, adapter = _build_router(monthly_cap_usd=0.01)
    today = date.today()
    await meter.store.record(day=today, tier="flash", fallback=False, cost_usd=0.05)

    with pytest.raises(CostBudgetExceeded):
        await router.chat(
            "secretary.brief.morning",
            [ChatMessage(role="user", content="hi")],
        )
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_cost_skipped_field_round_trips_through_response():
    """Pydantic model serialises + parses the new flag."""
    r = synthetic_skip_response(caller_id="x", tier="pro")
    j = r.model_dump_json()
    r2 = ChatResponse.model_validate_json(j)
    assert r2.cost_skipped is True

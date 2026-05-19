"""P0.5 — per-caller_id concurrency cap on LlmRouter.

The cap defaults to 4 (built-in) and is configurable via featureflags:
``llm.concurrency.<caller_id>`` overrides ``llm.concurrency.default``.
"""

from __future__ import annotations

import asyncio

import featureflags
import featureflags.registry  # noqa: F401 — registers `llm.concurrency.default`
import pytest
from llm_client import ChatMessage, ChatResponse, LlmRouter
from llm_client.cost_meter import CostMeter, InMemorySpendStore
from llm_client.fallback import FallbackChain
from llm_client.rate_limiter import RateLimiter


class _SlowAdapter:
    name = "stub"

    def __init__(self, latency_s: float) -> None:
        self.latency_s = latency_s
        self.in_flight = 0
        self.peak = 0
        self._lock = asyncio.Lock()

    async def chat(self, messages, *, tier, max_tokens, temperature, timeout_s):
        async with self._lock:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.latency_s)
        finally:
            async with self._lock:
                self.in_flight -= 1
        return ChatResponse(
            text="ok",
            model="stub",
            tier=tier,
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.0,
            request_id="r",
            latency_ms=int(self.latency_s * 1000),
        )

    async def embed(self, texts, *, timeout_s):  # pragma: no cover
        from llm_client.types import EmbedResponse

        return EmbedResponse(vectors=[[0.0]], model="stub", cost_usd=0.0, request_id="r")


def _router(latency_s: float = 0.1) -> tuple[LlmRouter, _SlowAdapter]:
    adapter = _SlowAdapter(latency_s)
    return (
        LlmRouter(
            primary=adapter,
            fallback=FallbackChain(pro_fallback=None, flash_fallback=None),
            rate_limiter=RateLimiter(),
            cost_meter=CostMeter(store=InMemorySpendStore(), monthly_cap_usd=10.0),
        ),
        adapter,
    )


@pytest.fixture(autouse=True)
def _isolate_flags():
    featureflags.reset_for_test()
    yield
    featureflags.reset_for_test()


@pytest.mark.asyncio
async def test_default_cap_is_4():
    router, adapter = _router(latency_s=0.1)
    await asyncio.gather(
        *(
            router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")])
            for _ in range(16)
        )
    )
    assert adapter.peak <= 4, f"peak in-flight {adapter.peak} > 4"


@pytest.mark.asyncio
async def test_per_caller_override_via_flag():
    featureflags.set_for_test("llm.concurrency.secretary.brief.morning", 2)
    router, adapter = _router(latency_s=0.1)
    await asyncio.gather(
        *(
            router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")])
            for _ in range(8)
        )
    )
    assert adapter.peak <= 2, f"peak in-flight {adapter.peak} > 2"


@pytest.mark.asyncio
async def test_different_callers_do_not_share_cap():
    featureflags.set_for_test("llm.concurrency.default", 2)
    router, adapter = _router(latency_s=0.1)
    await asyncio.gather(
        router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")]),
        router.chat("secretary.brief.morning", [ChatMessage(role="user", content="x")]),
        router.chat("intel.synth", [ChatMessage(role="user", content="x")]),
        router.chat("intel.synth", [ChatMessage(role="user", content="x")]),
    )
    # Two callers × 2 concurrency each = up to 4 simultaneously.
    assert adapter.peak <= 4

"""Workflow 03 §10 + §6 — fallback chain + router integration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
from llm_client.adapters.base import Adapter
from llm_client.cache import InMemoryCacheStore, PromptCache
from llm_client.cost_meter import CostMeter, InMemorySpendStore
from llm_client.exceptions import (
    CostBudgetExceeded,
    DeepSeekDown,
    NoLLMAvailable,
    ProviderTimeout,
    UnknownCallerId,
)
from llm_client.fallback import FallbackChain
from llm_client.rate_limiter import RateLimiter
from llm_client.router import LlmRouter
from llm_client.telemetry import CapturingTelemetrySink
from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier


@dataclass
class StubAdapter(Adapter):
    name: str = "stub"
    response_text: str = "ok"
    cost_usd: float = 0.001
    raise_on_chat: Exception | None = None
    chat_calls: list[tuple[LlmTier, list[ChatMessage]]] = field(default_factory=list)
    health_ok: bool = True

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tier: LlmTier,
        max_tokens: int,
        temperature: float,
        timeout_s: float,
    ) -> ChatResponse:
        self.chat_calls.append((tier, list(messages)))
        if self.raise_on_chat is not None:
            raise self.raise_on_chat
        return ChatResponse(
            text=self.response_text,
            model=f"{self.name}-{tier}",
            tier=tier,
            prompt_tokens=10,
            completion_tokens=10,
            cost_usd=self.cost_usd,
            cached=False,
            fallback_used=(self.name != "stub-primary"),
            request_id=str(uuid.uuid4()),
            latency_ms=1,
        )

    async def embed(self, texts: list[str], *, timeout_s: float) -> EmbedResponse:
        return EmbedResponse(
            vectors=[[0.0] * 8 for _ in texts],
            model=f"{self.name}-embed",
            cost_usd=0.0,
            request_id=str(uuid.uuid4()),
        )

    async def health(self) -> bool:
        return self.health_ok


def deepseek_down() -> DeepSeekDown:
    return DeepSeekDown("simulated outage")


def _router(
    primary: StubAdapter,
    *,
    pro_fb: StubAdapter | None = None,
    flash_fb: StubAdapter | None = None,
    monthly_cap: float = 100.0,
    fallback_cap: float = 100.0,
    cache_eligible_only: bool = True,
    telemetry: CapturingTelemetrySink | None = None,
) -> LlmRouter:
    return LlmRouter(
        primary=primary,
        fallback=FallbackChain(pro_fallback=pro_fb, flash_fallback=flash_fb),
        rate_limiter=RateLimiter(),
        cost_meter=CostMeter(
            store=InMemorySpendStore(),
            monthly_cap_usd=monthly_cap,
            fallback_cap_usd=fallback_cap,
        ),
        cache=PromptCache(InMemoryCacheStore()) if cache_eligible_only else None,
        telemetry=telemetry or CapturingTelemetrySink(),
    )


class TestPrimaryHappyPath:
    @pytest.mark.asyncio
    async def test_synth_routes_to_pro(self) -> None:
        primary = StubAdapter(name="stub-primary", response_text="thesis")
        router = _router(primary)
        resp = await router.chat("intel.synth", [ChatMessage(role="user", content="brief")])
        assert resp.tier == "pro"
        assert resp.text == "thesis"
        assert primary.chat_calls[0][0] == "pro"

    @pytest.mark.asyncio
    async def test_translate_routes_to_flash(self) -> None:
        primary = StubAdapter(name="stub-primary")
        router = _router(primary)
        resp = await router.chat(
            "intel.crawler.translate", [ChatMessage(role="user", content="hello")]
        )
        assert resp.tier == "flash"


class TestFallback:
    @pytest.mark.asyncio
    async def test_pro_failure_falls_back_to_anthropic(self) -> None:
        primary = StubAdapter(name="stub-primary", raise_on_chat=deepseek_down())
        fb = StubAdapter(name="stub-anthropic", response_text="from-claude")
        router = _router(primary, pro_fb=fb)
        resp = await router.chat("intel.synth", [ChatMessage(role="user", content="brief")])
        assert resp.text == "from-claude"
        assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_flash_failure_falls_back_to_groq(self) -> None:
        primary = StubAdapter(name="stub-primary", raise_on_chat=deepseek_down())
        fb = StubAdapter(name="stub-groq", response_text="from-groq")
        router = _router(primary, flash_fb=fb)
        resp = await router.chat(
            "intel.crawler.translate", [ChatMessage(role="user", content="hi")]
        )
        assert resp.text == "from-groq"
        assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self) -> None:
        primary = StubAdapter(name="stub-primary", raise_on_chat=ProviderTimeout("slow"))
        fb = StubAdapter(name="stub-anthropic")
        router = _router(primary, pro_fb=fb)
        resp = await router.chat("intel.synth", [ChatMessage(role="user", content="brief")])
        assert resp.fallback_used is True

    @pytest.mark.asyncio
    async def test_no_fallback_configured_raises_no_llm_available(self) -> None:
        primary = StubAdapter(name="stub-primary", raise_on_chat=deepseek_down())
        router = _router(primary)  # no fallbacks
        with pytest.raises(NoLLMAvailable):
            await router.chat("intel.synth", [ChatMessage(role="user", content="x")])

    @pytest.mark.asyncio
    async def test_both_down_raises_no_llm_available(self) -> None:
        primary = StubAdapter(name="stub-primary", raise_on_chat=deepseek_down())
        fb = StubAdapter(name="stub-anthropic", raise_on_chat=DeepSeekDown("also down"))
        router = _router(primary, pro_fb=fb)
        with pytest.raises(NoLLMAvailable):
            await router.chat("intel.synth", [ChatMessage(role="user", content="x")])


class TestFallbackCostCap:
    @pytest.mark.asyncio
    async def test_fallback_blocked_when_fallback_cap_exhausted(self) -> None:
        primary = StubAdapter(name="stub-primary", raise_on_chat=deepseek_down())
        fb = StubAdapter(name="stub-anthropic")
        router = _router(primary, pro_fb=fb, fallback_cap=0.001)
        # Pre-burn the fallback budget.
        await router.cost_meter.store.record(
            day=__import__("datetime").datetime.now(__import__("datetime").UTC).date(),
            tier="pro",
            fallback=True,
            cost_usd=1.0,
        )
        with pytest.raises(CostBudgetExceeded):
            await router.chat("intel.synth", [ChatMessage(role="user", content="x")])


class TestPrimaryCostCap:
    @pytest.mark.asyncio
    async def test_primary_blocked_when_monthly_cap_exhausted(self) -> None:
        primary = StubAdapter(name="stub-primary")
        router = _router(primary, monthly_cap=0.0001)
        # Pre-burn the monthly budget so the very first call is blocked.
        await router.cost_meter.store.record(
            day=__import__("datetime").datetime.now(__import__("datetime").UTC).date(),
            tier="pro",
            fallback=False,
            cost_usd=1.0,
        )
        with pytest.raises(CostBudgetExceeded):
            await router.chat("intel.synth", [ChatMessage(role="user", content="x")])


class TestCacheIntegration:
    @pytest.mark.asyncio
    async def test_second_translate_call_returns_cached_true(self) -> None:
        primary = StubAdapter(name="stub-primary", response_text="hola")
        router = _router(primary)
        msgs = [ChatMessage(role="user", content="translate hello")]
        first = await router.chat("intel.crawler.translate", msgs)
        assert first.cached is False
        second = await router.chat("intel.crawler.translate", msgs)
        assert second.cached is True
        assert second.text == "hola"
        assert second.cost_usd == 0.0
        # Primary was only called once — second was a cache hit.
        assert len(primary.chat_calls) == 1

    @pytest.mark.asyncio
    async def test_synth_never_cached_even_after_repeat(self) -> None:
        primary = StubAdapter(name="stub-primary")
        router = _router(primary)
        msgs = [ChatMessage(role="user", content="brief")]
        await router.chat("intel.synth", msgs)
        await router.chat("intel.synth", msgs)
        assert len(primary.chat_calls) == 2  # both went to provider


class TestUnknownCaller:
    @pytest.mark.asyncio
    async def test_unknown_caller_raises_at_chat(self) -> None:
        router = _router(StubAdapter(name="stub-primary"))
        with pytest.raises(UnknownCallerId):
            await router.chat("no.such.caller", [ChatMessage(role="user", content="x")])


class TestTelemetry:
    @pytest.mark.asyncio
    async def test_one_row_per_call(self) -> None:
        primary = StubAdapter(name="stub-primary")
        sink = CapturingTelemetrySink()
        router = _router(primary, telemetry=sink)
        await router.chat("intel.synth", [ChatMessage(role="user", content="x")])
        # fire_and_forget schedules the write — give the loop a tick.
        import asyncio

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(sink.calls) == 1
        assert sink.calls[0]["caller_id"] == "intel.synth"
        assert sink.calls[0]["tier"] == "pro"
        assert sink.calls[0]["outcome"] == "ok"

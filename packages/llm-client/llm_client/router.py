"""Public surface for IIC's LLM client (workflow 03 §5, §6).

Two callable shapes:
  - LlmRouter class — explicit dependency injection, used in tests and by
    callers that want their own adapters.
  - Module functions chat() / embed() — convenience wrappers around a
    process-wide singleton built from env. Most apps use these.

Runtime signals (filing_pages, regime_change, etc.) flow through a
ContextVar so callers don't have to thread them into every function.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from dataclasses import field as _field
from typing import Any

from llm_client._matrix import lookup, resolve_tier
from llm_client.adapters.base import Adapter
from llm_client.cache import PromptCache
from llm_client.cost_meter import CostMeter
from llm_client.exceptions import (
    CostBudgetExceeded,
    DeepSeekDown,
    NoLLMAvailable,
    ProviderError,
    ProviderTimeout,
)
from llm_client.fallback import FallbackChain
from llm_client.rate_limiter import RateLimiter
from llm_client.telemetry import (
    NullTelemetrySink,
    TelemetrySink,
    fire_and_forget,
)
from llm_client.types import ChatMessage, ChatResponse, EmbedResponse, LlmTier

_runtime_signals: ContextVar[dict[str, Any]] = ContextVar("iic_llm_runtime_signals", default={})


@asynccontextmanager
async def with_signals(**kwargs: Any) -> AsyncIterator[None]:
    """Push runtime signals (filing_pages=240, regime_change=True, …) into
    the matrix's escalation rules without fattening the public signature."""
    token = _runtime_signals.set({**_runtime_signals.get(), **kwargs})
    try:
        yield
    finally:
        _runtime_signals.reset(token)


def runtime_signals() -> Mapping[str, Any]:
    return _runtime_signals.get()


@dataclass(slots=True)
class LlmRouter:
    primary: Adapter
    fallback: FallbackChain
    rate_limiter: RateLimiter
    cost_meter: CostMeter
    cache: PromptCache | None = None
    telemetry: TelemetrySink = _field(default_factory=NullTelemetrySink)

    async def chat(
        self,
        caller_id: str,
        messages: list[ChatMessage],
        *,
        force_tier: LlmTier | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        timeout_s: float = 30.0,
    ) -> ChatResponse:
        spec = lookup(caller_id)
        tier: LlmTier = force_tier or resolve_tier(caller_id, runtime_signals())

        # Cache lookup (Flash deterministic callers only).
        if self.cache is not None and spec.cache_eligible and not force_tier:
            hit = await self.cache.get(caller_id, tier, messages)
            if hit is not None:
                fire_and_forget(
                    self.telemetry,
                    caller_id=caller_id,
                    request=messages,
                    response=hit,
                    outcome="ok",
                    error=None,
                )
                return hit

        # Cost gate.
        if not await self.cost_meter.allow():
            raise CostBudgetExceeded("monthly LLM budget exceeded; circuit breaker is OPEN")

        # Rate limit + primary attempt + fallback.
        await self.rate_limiter.acquire(provider=self.primary.name, tier=tier)
        try:
            try:
                response = await self.primary.chat(
                    messages,
                    tier=tier,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_s=timeout_s,
                )
            except (DeepSeekDown, ProviderTimeout) as exc:
                if not await self.cost_meter.allow(fallback=True):
                    raise CostBudgetExceeded(
                        "fallback cap exceeded while DeepSeek is down"
                    ) from exc
                response = await self.fallback.chat(
                    messages,
                    tier=tier,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_s=timeout_s,
                    primary_error=exc,
                )
        finally:
            self.rate_limiter.release(provider=self.primary.name, tier=tier)

        await self.cost_meter.record(response)
        fire_and_forget(
            self.telemetry,
            caller_id=caller_id,
            request=messages,
            response=response,
            outcome="ok",
            error=None,
        )

        if self.cache is not None and spec.cache_eligible and not force_tier:
            await self.cache.set(caller_id, tier, messages, response, spec.cache_ttl_seconds)
        return response

    async def embed(self, caller_id: str, texts: list[str]) -> EmbedResponse:
        # Sanity: the matrix entry must declare embed tier.
        spec = lookup(caller_id)
        if spec.default_tier != "embed":
            raise ProviderError(f"caller_id={caller_id} is not registered as an embed caller")
        if not await self.cost_meter.allow():
            raise CostBudgetExceeded("monthly LLM budget exceeded; circuit breaker is OPEN")
        await self.rate_limiter.acquire(provider=self.primary.name, tier="embed")
        try:
            return await self.primary.embed(texts, timeout_s=30.0)
        finally:
            self.rate_limiter.release(provider=self.primary.name, tier="embed")


# ---- module-level singleton + thin convenience wrappers --------------------

_default_router: LlmRouter | None = None


def set_router(router: LlmRouter | None) -> None:
    """Override the process-wide singleton. Tests use this to inject mocks."""
    global _default_router
    _default_router = router


def get_router() -> LlmRouter:
    if _default_router is None:
        raise NoLLMAvailable("no default router configured — call set_router() at app boot")
    return _default_router


async def chat(
    caller_id: str,
    messages: list[ChatMessage],
    *,
    force_tier: LlmTier | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.4,
    timeout_s: float = 30.0,
) -> ChatResponse:
    return await get_router().chat(
        caller_id,
        messages,
        force_tier=force_tier,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_s=timeout_s,
    )


async def embed(caller_id: str, texts: list[str]) -> EmbedResponse:
    return await get_router().embed(caller_id, texts)

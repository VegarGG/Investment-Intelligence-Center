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

import asyncio
import uuid
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

try:
    from featureflags import flag as _flag
    from featureflags import flag_value as _flag_value
except ImportError:  # pragma: no cover — featureflags is a runtime peer dep
    def _flag(_name: str) -> bool:
        return False

    def _flag_value(_name: str, default):  # type: ignore[no-untyped-def]
        return default

try:
    from opentelemetry import trace as _otel_trace

    _otel_tracer = _otel_trace.get_tracer("iic.llm_client.router")
except ImportError:  # pragma: no cover — otel is an optional runtime dep
    _otel_tracer = None  # type: ignore[assignment]


def _maybe_span(caller_id: str, tier: str | None):
    """Return a context-manager span if OTel is available, else a no-op."""
    if _otel_tracer is None:
        return _NullSpan()
    span = _otel_tracer.start_as_current_span(f"llm.chat:{caller_id}")
    return _SpanCtx(span, caller_id=caller_id, tier=tier)


class _NullSpan:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def set_attribute(self, *a, **kw): pass


class _SpanCtx:
    """Tiny wrapper that pumps relevant attributes into the OTel span (P9.1)."""

    __slots__ = ("_cm", "_span", "caller_id", "tier")

    def __init__(self, cm, *, caller_id: str, tier: str | None) -> None:
        self._cm = cm
        self._span = None
        self.caller_id = caller_id
        self.tier = tier

    def __enter__(self):
        self._span = self._cm.__enter__()
        if self._span is not None:
            self._span.set_attribute("iic.caller_id", self.caller_id)
            if self.tier:
                self._span.set_attribute("iic.tier", self.tier)
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._cm.__exit__(exc_type, exc, tb)

    def set_attribute(self, key: str, value):  # type: ignore[no-untyped-def]
        if self._span is not None:
            self._span.set_attribute(key, value)


def _cost_breaker_enabled() -> bool:
    """Module-local indirection so tests can override via featureflags.set_for_test."""
    return _flag("cost_breaker.enabled")


_DEFAULT_CALLER_CONCURRENCY = 4


def _caller_concurrency_cap(caller_id: str) -> int:
    """Resolve per-caller concurrency cap (P0.5).

    Lookup order:
    1. ``llm.concurrency.<caller_id>`` flag value (numeric).
    2. ``llm.concurrency.default`` flag value.
    3. Built-in ``_DEFAULT_CALLER_CONCURRENCY`` (4).
    """
    specific = _flag_value(f"llm.concurrency.{caller_id}", -1)
    if isinstance(specific, int) and specific > 0:
        return specific
    default = _flag_value("llm.concurrency.default", _DEFAULT_CALLER_CONCURRENCY)
    if isinstance(default, int) and default > 0:
        return default
    return _DEFAULT_CALLER_CONCURRENCY


class _CallerConcurrency:
    """Semaphore-per-caller_id with lazy creation.

    Caps the number of in-flight router calls per caller_id so a single
    runaway agent cannot saturate the provider rate-limit slots and
    starve its neighbours. The cap is read at acquisition time so flag
    updates take effect on the next call without requiring a router
    restart.
    """

    __slots__ = ("_sems", "_lock")

    def __init__(self) -> None:
        self._sems: dict[str, tuple[int, asyncio.Semaphore]] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, caller_id: str) -> asyncio.Semaphore:
        cap = _caller_concurrency_cap(caller_id)
        async with self._lock:
            existing = self._sems.get(caller_id)
            if existing is None or existing[0] != cap:
                sem = asyncio.Semaphore(cap)
                self._sems[caller_id] = (cap, sem)
            else:
                sem = existing[1]
        await sem.acquire()
        return sem

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


# v2.5 T1.9 — synthetic-skip response when the cost breaker is open. The
# `cost_skipped` flag travels through the response so downstream nodes can
# tag their advice as "synthetic-skip-tainted." Tests pin this string so the
# brief markdown can detect it.
COST_SKIPPED_MARKER = "[cost-breaker open: synthetic skip]"


def synthetic_skip_response(
    *, caller_id: str, tier: LlmTier, reason: str = "cost_breaker_open"
) -> "ChatResponse":
    """Build a `cost_skipped=True` ChatResponse the DAG can consume.

    Used by ``LlmRouter.chat_or_skip`` so cost-cap-tripped DAG nodes still
    return a valid response shape rather than raising mid-fanout.
    """
    return ChatResponse(
        text=COST_SKIPPED_MARKER,
        model=f"synthetic-skip:{reason}",
        tier=tier,
        prompt_tokens=0,
        completion_tokens=0,
        cost_usd=0.0,
        cached=False,
        fallback_used=False,
        cost_skipped=True,
        request_id=f"skip-{uuid.uuid4().hex[:12]}",
        latency_ms=0,
    )


@dataclass(slots=True)
class LlmRouter:
    primary: Adapter
    fallback: FallbackChain
    rate_limiter: RateLimiter
    cost_meter: CostMeter
    cache: PromptCache | None = None
    telemetry: TelemetrySink = _field(default_factory=NullTelemetrySink)
    caller_concurrency: _CallerConcurrency = _field(default_factory=_CallerConcurrency)

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

        # P9.1 — wrap the entire chat call in a span so every chat
        # produces a trace tagged with caller_id, tier, tokens, and cost.
        _span_cm = _maybe_span(caller_id, tier)

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

        # Cost gate. Emit telemetry before raising so every call is observed
        # in `lake.llm_calls` (P0.6).
        if not await self.cost_meter.allow():
            fire_and_forget(
                self.telemetry,
                caller_id=caller_id,
                request=messages,
                response=None,
                outcome="rate_limit",
                error="cost_breaker_open",
            )
            raise CostBudgetExceeded("monthly LLM budget exceeded; circuit breaker is OPEN")

        # P0.5 — per-caller concurrency cap. Hold the semaphore for the
        # full provider round-trip so the cap actually bounds in-flight.
        caller_sem = await self.caller_concurrency.acquire(caller_id)
        try:
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
                        fire_and_forget(
                            self.telemetry,
                            caller_id=caller_id,
                            request=messages,
                            response=None,
                            outcome="rate_limit",
                            error="fallback_cap_exceeded",
                        )
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
        except ProviderTimeout as exc:
            fire_and_forget(
                self.telemetry,
                caller_id=caller_id,
                request=messages,
                response=None,
                outcome="timeout",
                error=str(exc) or "provider_timeout",
            )
            raise
        except ProviderError as exc:
            fire_and_forget(
                self.telemetry,
                caller_id=caller_id,
                request=messages,
                response=None,
                outcome="error",
                error=str(exc) or "provider_error",
            )
            raise
        except CostBudgetExceeded:
            raise
        except Exception as exc:
            fire_and_forget(
                self.telemetry,
                caller_id=caller_id,
                request=messages,
                response=None,
                outcome="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        finally:
            caller_sem.release()

        await self.cost_meter.record(response)
        fire_and_forget(
            self.telemetry,
            caller_id=caller_id,
            request=messages,
            response=response,
            outcome="ok",
            error=None,
        )

        with _span_cm as span:
            span.set_attribute("iic.model", response.model)
            span.set_attribute("iic.tokens.in", response.prompt_tokens)
            span.set_attribute("iic.tokens.out", response.completion_tokens)
            span.set_attribute("iic.cost_usd", response.cost_usd)
            span.set_attribute("iic.outcome", "ok")
            span.set_attribute("iic.cached", response.cached)
            span.set_attribute("iic.fallback_used", response.fallback_used)

        if self.cache is not None and spec.cache_eligible and not force_tier:
            await self.cache.set(caller_id, tier, messages, response, spec.cache_ttl_seconds)
        return response

    async def chat_or_raise(
        self,
        caller_id: str,
        messages: list[ChatMessage],
        *,
        force_tier: LlmTier | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        timeout_s: float = 30.0,
    ) -> ChatResponse:
        """Chat that never substitutes a synthetic-skip placeholder (P0.2).

        Identical surface to ``chat`` — exists as a named alias so call
        sites that want explicit "raise on provider failure" semantics can
        be grepped, and so ``chat_or_skip`` has something to delegate to
        when ``cost_breaker.enabled`` is off.
        """
        return await self.chat(
            caller_id,
            messages,
            force_tier=force_tier,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )

    async def chat_or_skip(
        self,
        caller_id: str,
        messages: list[ChatMessage],
        *,
        force_tier: LlmTier | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        timeout_s: float = 30.0,
        drain_deadline_s: float = 30.0,
    ) -> ChatResponse:
        """v2.5 T1.9 — graceful-degrade chat.

        Behaviour with ``cost_breaker.enabled=False`` (P0 default): delegates
        straight to ``chat_or_raise``; provider failures surface as real
        exceptions so we can see them in development instead of returning
        synthetic-skip placeholders that silently taint every advice.

        Behaviour with ``cost_breaker.enabled=True``:
        - In-flight calls keep running, capped at ``drain_deadline_s``.
        - New calls return a `cost_skipped=True` ChatResponse so the DAG
          continues with synthetic-skip-tainted advice.
        - `with_signals(cost_breaker_open=True)` propagates the state to
          downstream nodes that consume `runtime_signals()`.
        """

        if not _cost_breaker_enabled():
            return await self.chat_or_raise(
                caller_id,
                messages,
                force_tier=force_tier,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_s=timeout_s,
            )

        if not await self.cost_meter.allow():
            fire_and_forget(
                self.telemetry,
                caller_id=caller_id,
                request=messages,
                response=None,
                outcome="rate_limit",
                error="cost_breaker_open",
            )
            return synthetic_skip_response(caller_id=caller_id, tier=force_tier or "flash")

        try:
            return await asyncio.wait_for(
                self.chat(
                    caller_id,
                    messages,
                    force_tier=force_tier,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_s=timeout_s,
                ),
                timeout=drain_deadline_s,
            )
        except CostBudgetExceeded:
            skip = synthetic_skip_response(caller_id=caller_id, tier=force_tier or "flash")
            fire_and_forget(
                self.telemetry,
                caller_id=caller_id,
                request=messages,
                response=skip,
                outcome="skipped",
                error="cost_breaker_open",
            )
            return skip
        except TimeoutError:
            skip = synthetic_skip_response(
                caller_id=caller_id, tier=force_tier or "flash", reason="drain_deadline"
            )
            fire_and_forget(
                self.telemetry,
                caller_id=caller_id,
                request=messages,
                response=skip,
                outcome="skipped",
                error="drain_deadline",
            )
            return skip

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


async def chat_or_skip(
    caller_id: str,
    messages: list[ChatMessage],
    *,
    force_tier: LlmTier | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.4,
    timeout_s: float = 30.0,
    drain_deadline_s: float = 30.0,
) -> ChatResponse:
    return await get_router().chat_or_skip(
        caller_id,
        messages,
        force_tier=force_tier,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_s=timeout_s,
        drain_deadline_s=drain_deadline_s,
    )


async def chat_or_raise(
    caller_id: str,
    messages: list[ChatMessage],
    *,
    force_tier: LlmTier | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.4,
    timeout_s: float = 30.0,
) -> ChatResponse:
    return await get_router().chat_or_raise(
        caller_id,
        messages,
        force_tier=force_tier,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_s=timeout_s,
    )


async def embed(caller_id: str, texts: list[str]) -> EmbedResponse:
    return await get_router().embed(caller_id, texts)

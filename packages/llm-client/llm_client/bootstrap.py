"""Env-driven LlmRouter construction (D7.1 §H0.1).

D7 shipped the router, adapters, rate-limiter, cost-meter and telemetry
sink, but never the glue that wires them together at agent boot. The
result was the v2.6 bringup state: every container healthy, every key
validated, and ``SELECT COUNT(*) FROM lake.llm_calls = 0`` because no
agent had called :func:`llm_client.set_router`.

This module is the single source of truth for "construct a router from
env." Every agent calls :func:`bootstrap_router_or_die` (or
:func:`router_from_env` for ingest-only services) inside its FastAPI
lifespan hook.

Reads (all optional except where noted):

    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL_PRO, DEEPSEEK_MODEL_FLASH, DEEPSEEK_MODEL_EMBED
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL
    GROQ_API_KEY, GROQ_MODEL
    LLM_MONTHLY_CAP_USD, LLM_FALLBACK_CAP_USD  (consumed by CostMeter defaults)
    LAKE_DSN  (telemetry sink; if unset we fall back to NullTelemetrySink
              so smoke environments without a lake still produce a router)
"""

from __future__ import annotations

import logging
import os

from llm_client.adapters.anthropic import AnthropicAdapter
from llm_client.adapters.base import Adapter
from llm_client.adapters.deepseek import DeepSeekAdapter
from llm_client.adapters.groq import GroqAdapter
from llm_client.cost_meter import CostMeter, InMemorySpendStore
from llm_client.fallback import FallbackChain
from llm_client.rate_limiter import RateLimiter
from llm_client.router import LlmRouter, current_router, set_router
from llm_client.telemetry import (
    NullTelemetrySink,
    PostgresTelemetrySink,
    TelemetrySink,
)

log = logging.getLogger(__name__)


def _build_primary() -> Adapter | None:
    """DeepSeek is the primary provider when its key is set. Falls through
    to Anthropic or Groq as a primary if DeepSeek is absent — this keeps
    a lone-Anthropic dev box bootable.
    """
    if key := os.environ.get("DEEPSEEK_API_KEY"):
        return DeepSeekAdapter(
            api_key=key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model_pro=os.environ.get("DEEPSEEK_MODEL_PRO", "deepseek-v4-pro"),
            model_flash=os.environ.get("DEEPSEEK_MODEL_FLASH", "deepseek-v4-flash"),
            embed_model=os.environ.get("DEEPSEEK_MODEL_EMBED", "deepseek-bge-m3"),
        )
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicAdapter(
            api_key=key,
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        )
    if key := os.environ.get("GROQ_API_KEY"):
        return GroqAdapter(
            api_key=key,
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        )
    return None


def _build_fallback_chain() -> FallbackChain:
    pro: Adapter | None = None
    flash: Adapter | None = None
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        pro = AnthropicAdapter(
            api_key=key,
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        )
    if key := os.environ.get("GROQ_API_KEY"):
        flash = GroqAdapter(
            api_key=key,
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        )
    return FallbackChain(pro_fallback=pro, flash_fallback=flash)


def _resolve_lake_dsn() -> str | None:
    """Find a usable async DSN for the telemetry sink.

    Precedence (first hit wins):
      1. ``LAKE_DSN`` — explicit override, used as-is. Operator-facing.
      2. ``IIC_PG_DSN_APP`` — the app-role DSN every agent already has
         injected via the iic-base compose env. Scheme is rewritten to
         ``postgresql+asyncpg://`` so sqlalchemy picks the async driver
         instead of psycopg2 (which would deadlock the event loop).
      3. ``POSTGRES_{USER,PASSWORD,HOST,PORT,DB}`` — last-resort build
         from individual env vars so a hand-rolled compose without
         IIC_PG_DSN_APP still gets telemetry persistence.

    Returns None only if none of the above are populated. That was the
    v2.6 bringup state: every agent had IIC_PG_DSN_APP but bootstrap
    only knew about LAKE_DSN, so the sink silently NullTelemetrySink'd
    and ``lake.llm_calls`` stayed at 0 (the D7.1 §H0.3 smoke gate
    couldn't see it because it asserts via psql, not via the sink).
    """
    if dsn := os.environ.get("LAKE_DSN"):
        return dsn
    if dsn := os.environ.get("IIC_PG_DSN_APP"):
        # `postgresql://` → `postgresql+asyncpg://`. Idempotent if the
        # operator already supplied the +asyncpg form.
        if dsn.startswith("postgresql+"):
            return dsn
        if dsn.startswith("postgresql://"):
            return "postgresql+asyncpg://" + dsn[len("postgresql://") :]
        if dsn.startswith("postgres://"):
            return "postgresql+asyncpg://" + dsn[len("postgres://") :]
        return dsn
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST")
    db = os.environ.get("POSTGRES_DB")
    if user and password and host and db:
        port = os.environ.get("POSTGRES_PORT", "5432")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
    return None


def _build_telemetry_sink() -> TelemetrySink:
    """PostgresTelemetrySink if we can resolve a DSN, else NullTelemetrySink.

    The smoke gate (D7.1 §H0.3) asserts on ``lake.llm_calls`` directly, so
    a deploy that wants real wiring observability needs Postgres reachable
    AND the iic_app role to have INSERT on lake.llm_calls (migration 0001
    grants it). Dev / unit-test environments without a DSN fall through to
    the null sink — the router still works, telemetry just drops on the
    floor.
    """
    dsn = _resolve_lake_dsn()
    if not dsn:
        log.info(
            "telemetry: no LAKE_DSN / IIC_PG_DSN_APP / POSTGRES_* resolved; "
            "using NullTelemetrySink — lake.llm_calls will not receive rows"
        )
        return NullTelemetrySink()
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        engine = create_async_engine(dsn, pool_pre_ping=True, pool_recycle=600)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        log.info("telemetry: PostgresTelemetrySink built (DSN host=%s)", _dsn_host(dsn))
        return PostgresTelemetrySink(sessionmaker=sm)
    except Exception as exc:  # pragma: no cover — defensive at boot
        log.warning(
            "telemetry: failed to build PostgresTelemetrySink from resolved DSN (%s); "
            "falling back to NullTelemetrySink",
            exc,
        )
        return NullTelemetrySink()


def _dsn_host(dsn: str) -> str:
    """Best-effort host extraction for log lines — never raises."""
    try:
        after_at = dsn.split("@", 1)[1]
        return after_at.split("/", 1)[0]
    except (IndexError, AttributeError):
        return "?"


def router_from_env() -> LlmRouter | None:
    """Construct an LlmRouter from environment variables, or return None
    if no LLM provider is configured.

    Returns None (rather than raising) so ingest-only services that are
    happy to run in a degraded mode can opt out — see the strict-vs-optional
    matrix in D7.1 §H0.2.
    """
    primary = _build_primary()
    if primary is None:
        return None

    return LlmRouter(
        primary=primary,
        fallback=_build_fallback_chain(),
        rate_limiter=RateLimiter(),
        cost_meter=CostMeter(store=InMemorySpendStore()),
        telemetry=_build_telemetry_sink(),
    )


def bootstrap_router_or_die(service_name: str) -> LlmRouter:
    """Strict-mode entry point: build a router from env, call
    :func:`set_router` so the legacy module-level ``chat()`` callers see
    the same instance, and raise with a clear message if no provider is
    configured. Use this in every agent that cannot do its job without an
    LLM (secretary, persona, fundamental, board).
    """
    router = router_from_env()
    if router is None:
        raise RuntimeError(
            f"{service_name}: no LLM provider configured. "
            "Set at least one of DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / "
            "GROQ_API_KEY in the service environment. See D7.1 §H0."
        )
    set_router(router)
    return router


def bootstrap_router_optional(service_name: str) -> LlmRouter | None:
    """Optional-mode entry point: same as :func:`router_from_env`, but
    also calls :func:`set_router` so module-level ``chat()`` callers
    inside this process pick up the instance. Returns None if no provider
    is configured — caller is expected to gate LLM-bound paths.
    """
    router = router_from_env()
    if router is None:
        log.info(
            "%s: no LLM provider configured; running in degraded (non-LLM) mode",
            service_name,
        )
        return None
    set_router(router)
    return router


def lifespan_bootstrap(service_name: str, *, strict: bool) -> LlmRouter | None:
    """FastAPI-lifespan-safe wrapper around the bootstrap functions.

    If a router is already installed (e.g. a test fixture pre-loaded a
    stub via :func:`set_router`), this is a no-op and the existing router
    is returned. Otherwise it delegates to :func:`bootstrap_router_or_die`
    or :func:`bootstrap_router_optional` based on ``strict``.

    This is the shape every agent's lifespan hook should call — it lets
    the strict-mode contract from D7.1 §H0.2 coexist with the
    ``set_router(stub)`` pattern that every agent's conftest uses.
    """
    existing = current_router()
    if existing is not None:
        return existing
    if strict:
        return bootstrap_router_or_die(service_name)
    return bootstrap_router_optional(service_name)

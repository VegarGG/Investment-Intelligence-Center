"""Per-key thin wrappers over the data_bus KV adapter (workflow 06 §2.5).

The data_bus package owns the raw NATS KV machinery; this module is the
typed surface the orchestrator uses to read/write the canonical
`iic_state` keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from nats.js.client import JetStreamContext

KEY_MACRO_REGIME = "macro_regime"
KEY_VIX_QUINTILE = "vix_quintile"
KEY_COST_BREAKER = "cost_breaker_state"
KEY_EVAL_DRIFT = "eval_drift_flag"
KEY_LAST_BRIEF_AT = "last_brief_at"

CostBreakerState = Literal["closed", "open", "half_open"]


async def get_macro_regime(js: JetStreamContext) -> str | None:
    from data_bus.kv import get

    return await get(js, "iic_state", KEY_MACRO_REGIME)


async def set_macro_regime(js: JetStreamContext, value: str) -> int:
    from data_bus.kv import put

    return await put(js, "iic_state", KEY_MACRO_REGIME, value)


async def get_cost_breaker_state(js: JetStreamContext) -> CostBreakerState:
    from data_bus.kv import get

    raw = await get(js, "iic_state", KEY_COST_BREAKER) or "closed"
    if raw not in ("closed", "open", "half_open"):
        return "closed"
    return raw  # type: ignore[return-value]


async def set_cost_breaker_state(js: JetStreamContext, value: CostBreakerState) -> int:
    from data_bus.kv import put

    return await put(js, "iic_state", KEY_COST_BREAKER, value)


async def set_last_brief_at(js: JetStreamContext, iso_ts: str) -> int:
    from data_bus.kv import put

    return await put(js, "iic_state", KEY_LAST_BRIEF_AT, iso_ts)

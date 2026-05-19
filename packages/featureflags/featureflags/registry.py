"""Canonical flag registry — every IIC v2.5 flag declared in one place.

Importing this module registers all v2.5 flags at startup. `docs/featureflags.md`
is generated from this registry; CI drift-checks doc vs registry.
"""

from __future__ import annotations

from .core import register

# T0.1 acceptance: at least one flag registered + observable.
register(
    name="iic.featureflags.bootstrap",
    description="Synthetic flag flipped by the T0.1 acceptance test.",
    added_in="v2.5-T0.1",
    default=False,
    owner="platform",
)

# T1.1 — live mark resolution toggle. Default ON; flipped OFF in chaos tests.
register(
    name="persona.live_mark.enabled",
    description="Use live mark from data_lake.quotes.get_mark in persona advice.",
    added_in="v2.5-T1.1",
    default=True,
    owner="persona",
)

# T1.4 — durable redelivery for the notifier. Default OFF until T1.4b ships.
register(
    name="notifier.durable_redelivery.enabled",
    description="Push NotifyExhausted onto Redis retry queue with severity-based TTL.",
    added_in="v2.5-T1.4",
    default=False,
    owner="notifier",
)

# T1.6 — per-agent circuit breaker on HttpxAgentClient.
register(
    name="orchestrator.agent_breaker.enabled",
    description="Open circuit after 5 consecutive failures; half-open every 60 s.",
    added_in="v2.5-T1.6",
    default=True,
    owner="orchestrator",
)

# T2.0 — NATS request-reply fan-out instead of HTTP. Per-DAG opt-in.
register(
    name="orchestrator.use_nats_for_agent_calls",
    description="Route agent fan-out via NATS request-reply instead of HTTP.",
    added_in="v2.5-T2.0",
    default=False,
    owner="orchestrator",
)

# T2.1 — wake the trading-room from intel.event.high_impact.v1.
register(
    name="trading_room.event_triage.enabled",
    description="Enable the Event-Triage Gate to fan out to analysis teams.",
    added_in="v2.5-T2.1",
    default=False,
    owner="trading_room",
)

# T2.4 — Investment Board sub-system.
register(
    name="trading_room.investment_board.enabled",
    description="Run Bull/Bear → 3-way Risk → Chair on every high-impact event.",
    added_in="v2.5-T2.4",
    default=False,
    owner="board",
)

# T2.7 — FUTU OpenAPI integration. Read-only by construction; flag also gates audit log.
register(
    name="agent_futu.enabled",
    description="Enable agent_futu container; read-only across N OpenD instances.",
    added_in="v2.5-T2.7",
    default=False,
    owner="agent_futu",
)

# P0 — Cost breaker gating. Default OFF: until we have real spend data, do not
# short-circuit calls to synthetic-skip; expose real provider failures instead.
register(
    name="cost_breaker.enabled",
    description=(
        "When true, LlmRouter.chat_or_skip gates calls on cost cap and falls back "
        "to a synthetic-skip response. Default off so production runs hit real "
        "providers and surface real failures."
    ),
    added_in="v2.6-P0",
    default=False,
    owner="platform",
)

# P0.5 — Per-caller_id concurrency cap. Numeric flag (use flag_value).
register(
    name="llm.concurrency.default",
    description=(
        "Max in-flight LlmRouter calls per caller_id. Prevents a runaway "
        "agent from saturating provider rate-limit slots and starving "
        "neighbours. Override per-caller via `llm.concurrency.<caller_id>`."
    ),
    added_in="v2.6-P0",
    default=4,
    owner="platform",
)

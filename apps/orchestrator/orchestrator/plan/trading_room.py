"""Trading-room DAG (v2.5 N3.5 / T2.8).

Wires the full event-driven trading-room flow:

    intel.event.high_impact.v1
      → Event-Triage Gate (event_triage.py)
      → fan-out to {Quant, Fundamental, Persona} /team_plan endpoints
      → Investment Board (Bull/Bear → Risk → Chair)
      → Trading-room brief (secretary.outbound.trading_room_brief)
      → Notify (severity=ALERT)

Idempotency: the trigger_event_id is the dedupe key. Re-runs of the
same event are no-ops (the orchestrator's existing idempotency cache
handles this; this DAG just plumbs the key through).

Failure isolation:
  - If a single team's /team_plan call breakers open, that slot is
    "team unavailable" and the Board considers the remaining N-1 plans.
  - If Bull/Bear returns junk (cost-skipped), Chair falls back to
    deterministic single-team-plan mode (highest-confidence wins).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import ulid

from ..execute.runner import StateGraph
from .agent_client import AgentClient
from .event_triage import triage

log = logging.getLogger(__name__)


@dataclass(slots=True)
class TradingRoomState:
    trace_id: str
    trigger_event: dict[str, Any] = field(default_factory=dict)
    triage_decision: dict[str, Any] | None = None
    plans: list[dict[str, Any]] = field(default_factory=list)
    team_failures: list[str] = field(default_factory=list)
    board_decision: dict[str, Any] | None = None
    brief_md: str | None = None
    notify_result: dict[str, Any] | None = None
    degraded: bool = False
    degraded_reasons: list[str] = field(default_factory=list)


def make_initial_state(
    *,
    trigger_event: dict[str, Any],
    trace_id: str | None = None,
) -> TradingRoomState:
    return TradingRoomState(
        trace_id=trace_id or trigger_event.get("trace_id") or str(ulid.ULID()),
        trigger_event=dict(trigger_event),
    )


def build_trading_room_dag(client: AgentClient) -> StateGraph[TradingRoomState]:
    """Build the trading-room DAG bound to the supplied agent client."""

    g: StateGraph[TradingRoomState] = StateGraph("trading_room")

    # ---- n_triage ----------------------------------------------------------
    async def n_triage(state: TradingRoomState) -> dict[str, Any]:
        decision = await triage(state.trigger_event)
        state.triage_decision = decision.to_dict()
        return {
            "node": "n_triage",
            "route": decision.route,
            "reason": decision.reason,
        }

    g.add_node("n_triage", n_triage)

    # ---- n_fanout: call Quant, Fundamental, Persona /team_plan -------------
    async def n_fanout(state: TradingRoomState) -> dict[str, Any]:
        if (state.triage_decision or {}).get("route") != "trading_room":
            # Triage decided not to wake the room — short-circuit.
            return {"node": "n_fanout", "skipped": True}

        targets = ("agent_quant", "agent_fundamental", "agent_persona")
        request_payload = {
            "action": "team_plan",
            "trace_id": state.trace_id,
            "trigger_event_id": state.trigger_event.get("event_id"),
            "tickers": state.trigger_event.get("tickers") or [],
        }

        for agent in targets:
            try:
                response = await client.call(agent, request_payload)
            except Exception as exc:  # noqa: BLE001 — degrade per-team
                log.warning("trading_room: %s call raised %s", agent, exc)
                state.team_failures.append(agent)
                state.degraded_reasons.append(f"{agent}_call_raised")
                continue
            if response.get("_breaker_open"):
                state.team_failures.append(agent)
                state.degraded_reasons.append(f"{agent}_breaker_open")
                continue
            plan = response.get("plan")
            if plan:
                state.plans.append(plan)

        if state.team_failures:
            state.degraded = True

        return {
            "node": "n_fanout",
            "plans_n": len(state.plans),
            "failures": list(state.team_failures),
        }

    g.add_node("n_fanout", n_fanout)

    # ---- n_board: Investment Board synthesis -------------------------------
    async def n_board(state: TradingRoomState) -> dict[str, Any]:
        if not state.plans:
            state.degraded = True
            state.degraded_reasons.append("no_plans_for_board")
            return {"node": "n_board", "skipped": True}

        response = await client.call(
            "agent_board",
            {
                "trigger_event_id": state.trigger_event.get("event_id"),
                "trace_id": state.trace_id,
                "plans": state.plans,
                "persist": True,
            },
        )
        if response.get("_breaker_open"):
            state.degraded = True
            state.degraded_reasons.append("board_breaker_open")
            return {"node": "n_board", "skipped": True}

        decision = response.get("decision")
        if decision is None:
            state.degraded = True
            state.degraded_reasons.append("board_no_decision")
            return {"node": "n_board", "skipped": True}

        state.board_decision = decision
        if response.get("degraded"):
            state.degraded = True
            state.degraded_reasons.append("board_degraded")

        return {
            "node": "n_board",
            "chosen_plan_id": decision.get("chosen_plan_id"),
            "confidence": decision.get("confidence"),
        }

    g.add_node("n_board", n_board)

    # ---- n_brief: secretary composes the markdown brief --------------------
    async def n_brief(state: TradingRoomState) -> dict[str, Any]:
        if state.board_decision is None:
            return {"node": "n_brief", "skipped": True}

        response = await client.call(
            "agent_secretary",
            {
                "action": "trading_room_brief",
                "trace_id": state.trace_id,
                "decision": state.board_decision,
                "considered_plans": state.plans,
                "degraded": state.degraded,
                "degraded_reasons": list(state.degraded_reasons),
            },
        )
        state.brief_md = response.get("markdown")
        return {
            "node": "n_brief",
            "char_count": len(state.brief_md or ""),
        }

    g.add_node("n_brief", n_brief)

    # ---- n_notify: push at severity=ALERT (lower than CRITICAL) ------------
    async def n_notify(state: TradingRoomState) -> dict[str, Any]:
        if not state.brief_md:
            return {"node": "n_notify", "skipped": True}
        try:
            state.notify_result = await client.call(
                "agent_secretary",
                {
                    "action": "notify",
                    "severity": "ALERT",
                    "trace_id": state.trace_id,
                    "markdown": state.brief_md,
                },
            )
        except Exception as exc:
            return {
                "node": "n_notify",
                "skipped": False,
                "deferred": True,
                "error": str(exc),
            }
        return {"node": "n_notify", "skipped": False}

    g.add_node("n_notify", n_notify)

    g.set_entry("n_triage")
    g.add_edge("n_triage", "n_fanout")
    g.add_edge("n_fanout", "n_board")
    g.add_edge("n_board", "n_brief")
    g.add_edge("n_brief", "n_notify")
    return g

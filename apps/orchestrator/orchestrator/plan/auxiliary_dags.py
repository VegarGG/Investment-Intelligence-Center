"""v2.5 T1.5 — DAGs for the four cron entries that v2.1 silently dropped.

`register_default_dags()` in `app.py` wires these alongside the morning
brief so every cron tick maps to a registered DAG. The
`test_registered_dags_match_cron.py` fail-closed test enforces it.

These DAGs are intentionally lightweight (1-3 nodes each) — they are the
heartbeat surface that downstream subscribers depend on, not full
fan-out workflows like the morning brief.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import ulid

from ..execute.runner import StateGraph
from ..execute.sla import SLA_TABLE
from .agent_client import AgentClient


@dataclass(slots=True)
class _SimpleState:
    trace_id: str
    macro_regime: str = "unknown"
    digest: dict[str, Any] | None = None
    advices: list[dict[str, Any]] = field(default_factory=list)
    notify_payload: dict[str, Any] | None = None


def _initial(trace_id: str | None = None) -> _SimpleState:
    return _SimpleState(trace_id=trace_id or str(ulid.ULID()))


# ---- midday_pulse -----------------------------------------------------------
def build_midday_pulse_dag(client: AgentClient) -> StateGraph[_SimpleState]:
    """Light Intel re-fetch + Quant regime check + Secretary one-line WeCom push
    if the regime changed.

    No persona fan-out, no LLM-heavy work — by design (plan §T1.5a).
    """
    g: StateGraph[_SimpleState] = StateGraph("midday_pulse")

    intel_soft, intel_hard = SLA_TABLE.get("intel.synth", (60, 90))

    async def n_intel_pulse(state: _SimpleState) -> dict[str, Any]:
        digest = await client.call(
            "agent_intelligence",
            {"action": "synth", "trace_id": state.trace_id, "mode": "midday_pulse"},
        )
        state.digest = digest
        state.macro_regime = digest.get("macro_regime", "unknown")
        return {"node": "n_intel_pulse", "macro_regime": state.macro_regime}

    g.add_node(
        "n_intel_pulse", n_intel_pulse, soft_timeout_s=intel_soft, hard_timeout_s=intel_hard
    )

    quant_soft, quant_hard = SLA_TABLE.get("quant.run", (60, 90))

    async def n_regime_check(state: _SimpleState) -> dict[str, Any]:
        result = await client.call(
            "agent_quant",
            {"action": "regime_check", "regime": state.macro_regime, "trace_id": state.trace_id},
        )
        state.notify_payload = {
            "macro_regime": state.macro_regime,
            "regime_changed": bool(result.get("changed", False)),
            "snapshot": result.get("snapshot"),
        }
        return {"node": "n_regime_check", "regime_changed": state.notify_payload["regime_changed"]}

    g.add_node(
        "n_regime_check", n_regime_check, soft_timeout_s=quant_soft, hard_timeout_s=quant_hard
    )

    async def n_notify_if_changed(state: _SimpleState) -> dict[str, Any]:
        if not (state.notify_payload and state.notify_payload.get("regime_changed")):
            return {"node": "n_notify_if_changed", "skipped": True}
        await client.call(
            "agent_secretary",
            {
                "action": "notify",
                "severity": "INFO",
                "trace_id": state.trace_id,
                "markdown": (
                    f"Midday regime check: macro_regime={state.macro_regime}. "
                    "Regime changed since the morning brief — review positions."
                ),
            },
        )
        return {"node": "n_notify_if_changed", "skipped": False}

    g.add_node("n_notify_if_changed", n_notify_if_changed)

    g.set_entry("n_intel_pulse")
    g.add_edge("n_intel_pulse", "n_regime_check")
    g.add_edge("n_regime_check", "n_notify_if_changed")
    return g


# ---- evening_recap ----------------------------------------------------------
def build_evening_recap_dag(client: AgentClient) -> StateGraph[_SimpleState]:
    """Backtest daily MTM + leaderboard delta + one-page recap brief (plan §T1.5b)."""
    g: StateGraph[_SimpleState] = StateGraph("evening_recap")

    bt_soft, bt_hard = SLA_TABLE.get("backtest.daily", (60, 120))

    async def n_backtest_mtm(state: _SimpleState) -> dict[str, Any]:
        result = await client.call(
            "agent_backtest",
            {"action": "daily_mtm", "trace_id": state.trace_id},
        )
        state.notify_payload = result
        return {"node": "n_backtest_mtm", "agents_n": len(result.get("agents", []))}

    g.add_node("n_backtest_mtm", n_backtest_mtm, soft_timeout_s=bt_soft, hard_timeout_s=bt_hard)

    sec_soft, sec_hard = SLA_TABLE.get("secretary.compose_brief", (30, 60))

    async def n_recap_brief(state: _SimpleState) -> dict[str, Any]:
        result = await client.call(
            "agent_secretary",
            {
                "action": "compose_brief",
                "kind": "evening_recap",
                "payload": state.notify_payload or {},
                "trace_id": state.trace_id,
            },
        )
        state.notify_payload = {**(state.notify_payload or {}), "markdown": result.get("markdown")}
        return {"node": "n_recap_brief", "char_count": len(result.get("markdown") or "")}

    g.add_node("n_recap_brief", n_recap_brief, soft_timeout_s=sec_soft, hard_timeout_s=sec_hard)

    async def n_recap_notify(state: _SimpleState) -> dict[str, Any]:
        markdown = (state.notify_payload or {}).get("markdown")
        if not markdown:
            return {"node": "n_recap_notify", "skipped": True}
        await client.call(
            "agent_secretary",
            {
                "action": "notify",
                "severity": "INFO",
                "markdown": markdown,
                "trace_id": state.trace_id,
            },
        )
        return {"node": "n_recap_notify", "skipped": False}

    g.add_node("n_recap_notify", n_recap_notify)

    g.set_entry("n_backtest_mtm")
    g.add_edge("n_backtest_mtm", "n_recap_brief")
    g.add_edge("n_recap_brief", "n_recap_notify")
    return g


# ---- hourly_intel_pulse -----------------------------------------------------
def build_hourly_intel_dag(client: AgentClient) -> StateGraph[_SimpleState]:
    """Intel agent hourly synthesize → push intel.digest.v1 (plan §T1.5c).

    This is the heartbeat for downstream subscribers (event-triage gate
    in T2 reads it). Intel publishes the digest itself; this DAG just
    triggers the synth and surfaces success / failure.
    """
    g: StateGraph[_SimpleState] = StateGraph("hourly_intel_pulse")

    intel_soft, intel_hard = SLA_TABLE.get("intel.synth", (60, 90))

    async def n_hourly_synth(state: _SimpleState) -> dict[str, Any]:
        digest = await client.call(
            "agent_intelligence",
            {"action": "synth", "mode": "hourly", "trace_id": state.trace_id},
        )
        state.digest = digest
        state.macro_regime = digest.get("macro_regime", "unknown")
        return {"node": "n_hourly_synth", "macro_regime": state.macro_regime}

    g.add_node(
        "n_hourly_synth", n_hourly_synth, soft_timeout_s=intel_soft, hard_timeout_s=intel_hard
    )

    g.set_entry("n_hourly_synth")
    return g


# ---- weekly_eval ------------------------------------------------------------
def build_weekly_eval_dag(client: AgentClient) -> StateGraph[_SimpleState]:
    """Run the prompt-eval golden set + emit leaderboard (plan §T1.5d)."""
    g: StateGraph[_SimpleState] = StateGraph("weekly_eval")

    bt_soft, bt_hard = SLA_TABLE.get("backtest.daily", (60, 120))

    async def n_eval_prompts(state: _SimpleState) -> dict[str, Any]:
        result = await client.call(
            "agent_backtest",
            {"action": "weekly_eval", "trace_id": state.trace_id},
        )
        state.notify_payload = result
        return {"node": "n_eval_prompts", "deltas_n": len(result.get("deltas", []))}

    g.add_node(
        "n_eval_prompts", n_eval_prompts, soft_timeout_s=bt_soft, hard_timeout_s=bt_hard
    )

    sec_soft, sec_hard = SLA_TABLE.get("secretary.compose_brief", (30, 60))

    async def n_publish_leaderboard(state: _SimpleState) -> dict[str, Any]:
        await client.call(
            "agent_secretary",
            {
                "action": "publish_leaderboard",
                "payload": state.notify_payload or {},
                "trace_id": state.trace_id,
            },
        )
        return {"node": "n_publish_leaderboard"}

    g.add_node(
        "n_publish_leaderboard",
        n_publish_leaderboard,
        soft_timeout_s=sec_soft,
        hard_timeout_s=sec_hard,
    )

    g.set_entry("n_eval_prompts")
    g.add_edge("n_eval_prompts", "n_publish_leaderboard")
    return g


# ---- NATS event DAGs --------------------------------------------------------
def build_intel_digest_event_dag(client: AgentClient) -> StateGraph[_SimpleState]:
    """`intel.digest.v1` event → re-fan-out to analysis teams.

    For T1.5 we only re-publish the regime hint to interested agents. The
    full event-driven trading-room fan-out lands in T2 once the
    Event-Triage Gate is in place.
    """
    g: StateGraph[_SimpleState] = StateGraph("event_intel_digest")

    async def n_route(state: _SimpleState) -> dict[str, Any]:
        await client.call(
            "agent_quant",
            {"action": "regime_hint", "trace_id": state.trace_id},
        )
        return {"node": "n_route"}

    g.add_node("n_route", n_route)
    g.set_entry("n_route")
    return g


def build_backtest_fill_event_dag(client: AgentClient) -> StateGraph[_SimpleState]:
    """`backtest.fill.v1` event → secretary push (plan §T1.5)."""
    g: StateGraph[_SimpleState] = StateGraph("event_backtest_fill")

    async def n_notify_fill(state: _SimpleState) -> dict[str, Any]:
        await client.call(
            "agent_secretary",
            {
                "action": "notify",
                "severity": "INFO",
                "trace_id": state.trace_id,
                "markdown": "Backtest fill recorded.",
            },
        )
        return {"node": "n_notify_fill"}

    g.add_node("n_notify_fill", n_notify_fill)
    g.set_entry("n_notify_fill")
    return g


def build_ops_alert_event_dag(client: AgentClient) -> StateGraph[_SimpleState]:
    """`ops.alert.v1` event → write a runbook hint to the dashboard (plan §T1.5)."""
    g: StateGraph[_SimpleState] = StateGraph("event_ops_alert")

    async def n_runbook_hint(state: _SimpleState) -> dict[str, Any]:
        await client.call(
            "agent_secretary",
            {
                "action": "runbook_hint",
                "trace_id": state.trace_id,
            },
        )
        return {"node": "n_runbook_hint"}

    g.add_node("n_runbook_hint", n_runbook_hint)
    g.set_entry("n_runbook_hint")
    return g


__all__ = [
    "build_backtest_fill_event_dag",
    "build_evening_recap_dag",
    "build_hourly_intel_dag",
    "build_intel_digest_event_dag",
    "build_midday_pulse_dag",
    "build_ops_alert_event_dag",
    "build_weekly_eval_dag",
    "_initial",
]

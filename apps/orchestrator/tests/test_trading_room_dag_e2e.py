"""v2.5 N3.5 / T2.8 — Trading-room DAG end-to-end (3 cases per plan §N3.5).

1. Happy path: synthetic high-impact event → brief out, all paths green.
2. One team's breaker is open: brief shows N-1 plans considered;
   Board still emits a decision.
3. Bull/Bear LLM call returns junk: Board falls back to "any single
   team's plan" mode and the brief notes the degraded state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import ulid
from featureflags import reset_for_test, set_for_test
from orchestrator.execute.runner import StateGraph, execute
from orchestrator.plan.agent_client import StubAgentClient
from orchestrator.plan.trading_room import (
    TradingRoomState,
    build_trading_room_dag,
    make_initial_state,
)


def _high_impact_event() -> dict[str, Any]:
    return {
        "event_id": "evt_e2e_001",
        "trace_id": "trace_e2e_001",
        "title": "FOMC cuts rates 50bps surprise",
        "body": "Powell: recession risk material; cuts not yet done.",
        "tickers": ["US.SPY", "US.AAPL"],
        "regime_change_score": 0.95,
        "surprise_factor": 0.95,
        "affected_universe_overlap": 0.9,
    }


def _quant_plan() -> dict[str, Any]:
    when = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
    return {
        "schema": "plan.v1",
        "id": str(ulid.ULID()),
        "team": "quant",
        "issued_at": when.isoformat(),
        "asset": {"kind": "equity", "ticker": "US.AAPL", "venue": "NASDAQ"},
        "action": "buy",
        "entry_price": 100.0,
        "entry_window_open": when.isoformat(),
        "entry_window_close": (when + timedelta(hours=4)).isoformat(),
        "target_price": 110.0,
        "stop_loss": 95.0,
        "max_drawdown_pct": 10.0,
        "horizon_days": 21,
        "sizing_pct_nav": 2.0,
        "confidence": 0.65,
        "thesis": "Quant net z=0.7.",
        "evidence": [{"kind": "factor", "ref": "quant.momentum"}],
        "expires_at": (when + timedelta(days=21)).isoformat(),
    }


def _fund_plan() -> dict[str, Any]:
    p = _quant_plan()
    p["id"] = str(ulid.ULID())
    p["team"] = "fundamental"
    p["target_price"] = 130.0
    p["stop_loss"] = 80.0
    p["confidence"] = 0.70
    p["horizon_days"] = 180
    p["evidence"] = [{"kind": "filing", "ref": "filing.AAPL_10Q"}]
    return p


def _persona_plan() -> dict[str, Any]:
    p = _quant_plan()
    p["id"] = str(ulid.ULID())
    p["team"] = "persona"
    p["persona_slug"] = "consensus"
    p["action"] = "hold"
    p["target_price"] = 100.0
    p["stop_loss"] = 100.0
    p["confidence"] = 0.30
    p["evidence"] = []
    p["disclaimer"] = "Not advice; persona consensus rollup."
    return p


def _board_decision(chosen_id: str, considered: list[str], confidence: float = 0.72) -> dict[str, Any]:
    return {
        "schema": "board.decision.v1",
        "id": str(ulid.ULID()),
        "trigger_event_id": "evt_e2e_001",
        "considered_plan_ids": considered,
        "chosen_plan_id": chosen_id,
        "chair_rationale": "Fundamental thesis dominates.",
        "dissent_record": (
            "Quant ([" + considered[0] + "]) wanted shorter horizon; "
            + (
                "persona ([" + considered[2] + "]) preferred hold."
                if len(considered) >= 3
                else "(no third plan considered)"
            )
        ),
        "risk_view": "Aggressive 5% vs Conservative 1.5%; Chair adopts 3%.",
        "confidence": confidence,
        "issued_at": datetime(2026, 5, 10, 12, 0, tzinfo=UTC).isoformat(),
    }


async def _run_dag(
    dag: StateGraph[TradingRoomState], state: TradingRoomState
) -> tuple[Any, TradingRoomState]:
    result = await execute(dag, state, trace_id=state.trace_id)
    return result, state


@pytest.fixture(autouse=True)
def _enable_flag():
    set_for_test("trading_room.event_triage.enabled", True)
    set_for_test("trading_room.investment_board.enabled", True)
    yield
    reset_for_test()


@pytest.mark.asyncio
async def test_happy_path_emits_brief_with_three_plans() -> None:
    quant, fund, persona = _quant_plan(), _fund_plan(), _persona_plan()
    chosen = fund["id"]
    decision = _board_decision(
        chosen_id=chosen, considered=[quant["id"], fund["id"], persona["id"]]
    )

    client = StubAgentClient(
        responses={
            "agent_quant": {"agent": "agent_quant", "ok": True, "plan": quant},
            "agent_fundamental": {"agent": "agent_fundamental", "ok": True, "plan": fund},
            "agent_persona": {"agent": "agent_persona", "ok": True, "plan": persona},
            "agent_board": {
                "status": "ok",
                "decision": decision,
                "degraded": False,
            },
            "agent_secretary": {
                "ok": True,
                "markdown": "# Trading Room — US.AAPL\n(brief body)",
            },
        }
    )
    dag = build_trading_room_dag(client)
    state = make_initial_state(trigger_event=_high_impact_event())
    result, state = await _run_dag(dag, state)

    assert result.ok, result
    assert state.triage_decision and state.triage_decision["route"] == "trading_room"
    assert len(state.plans) == 3
    assert state.board_decision is not None
    assert state.board_decision["chosen_plan_id"] == chosen
    assert state.brief_md and "Trading Room" in state.brief_md
    assert state.degraded is False
    # Notify ran at severity ALERT.
    notify_call = next(c for c in client.calls if c[0] == "agent_secretary" and c[1].get("action") == "notify")
    assert notify_call[1]["severity"] == "ALERT"


@pytest.mark.asyncio
async def test_one_team_breakered_open_brief_shows_n_minus_one_plans() -> None:
    quant, fund = _quant_plan(), _fund_plan()
    chosen = fund["id"]
    decision = _board_decision(chosen_id=chosen, considered=[quant["id"], fund["id"]])

    client = StubAgentClient(
        responses={
            "agent_quant": {"agent": "agent_quant", "ok": True, "plan": quant},
            "agent_fundamental": {"agent": "agent_fundamental", "ok": True, "plan": fund},
            # Persona breakered open.
            "agent_persona": {
                "agent": "agent_persona",
                "ok": False,
                "advices": [],
                "_breaker_open": True,
                "_target": "agent_persona",
            },
            "agent_board": {
                "status": "ok",
                "decision": decision,
                "degraded": False,
            },
            "agent_secretary": {
                "ok": True,
                "markdown": "# Trading Room (degraded)\n",
            },
        }
    )
    dag = build_trading_room_dag(client)
    state = make_initial_state(trigger_event=_high_impact_event())
    result, state = await _run_dag(dag, state)

    assert result.ok
    assert len(state.plans) == 2
    assert "agent_persona" in state.team_failures
    assert state.degraded is True
    assert "agent_persona_breaker_open" in state.degraded_reasons
    assert state.board_decision is not None
    assert state.board_decision["chosen_plan_id"] == chosen


@pytest.mark.asyncio
async def test_bull_bear_junk_board_runs_in_degraded_mode() -> None:
    quant, fund, persona = _quant_plan(), _fund_plan(), _persona_plan()
    # Board self-reports degraded=True but still emits a fallback decision.
    decision = _board_decision(
        chosen_id=fund["id"],
        considered=[quant["id"], fund["id"], persona["id"]],
        confidence=fund["confidence"],
    )
    decision["chair_rationale"] = (
        "Fallback selection (bull_bear_degraded): chose plan on highest confidence."
    )

    client = StubAgentClient(
        responses={
            "agent_quant": {"agent": "agent_quant", "ok": True, "plan": quant},
            "agent_fundamental": {"agent": "agent_fundamental", "ok": True, "plan": fund},
            "agent_persona": {"agent": "agent_persona", "ok": True, "plan": persona},
            "agent_board": {
                "status": "ok",
                "decision": decision,
                "degraded": True,
            },
            "agent_secretary": {
                "ok": True,
                "markdown": "# Trading Room (board degraded)\n",
            },
        }
    )
    dag = build_trading_room_dag(client)
    state = make_initial_state(trigger_event=_high_impact_event())
    result, state = await _run_dag(dag, state)

    assert result.ok
    assert state.board_decision is not None
    assert "Fallback" in state.board_decision["chair_rationale"]
    assert state.degraded is True
    assert "board_degraded" in state.degraded_reasons

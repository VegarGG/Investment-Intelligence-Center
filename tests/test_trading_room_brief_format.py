"""v2.5 N3.4 / T2.6 — Trading-room brief snapshot format.

Whitespace-tolerant comparison against the golden Markdown so cosmetic
LF / spacing changes don't break the gate but structural drift does.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import ulid
from schema.advice import Asset, Evidence
from schema.plan import PlanV1
from secretary.outbound.trading_room_brief import compose_trading_room_brief

GOLDEN = Path(__file__).resolve().parent / "fixtures/trading_room/golden_brief_001.md"


def _normalize(s: str) -> str:
    """Collapse runs of whitespace to single spaces; keep newlines as line breaks."""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in s.strip().splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _build_fixture() -> tuple[dict, list[PlanV1]]:
    asset = Asset(kind="equity", ticker="US.AAPL", venue="NASDAQ")
    when = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

    quant = PlanV1(
        id=str(ulid.ULID()),
        team="quant",
        persona_slug=None,
        issued_at=when,
        asset=asset,
        action="buy",
        entry_price=100.0,
        entry_window_open=when,
        entry_window_close=when + timedelta(hours=4),
        target_price=110.0,
        stop_loss=95.0,
        max_drawdown_pct=10.0,
        horizon_days=21,
        sizing_pct_nav=2.0,
        confidence=0.65,
        thesis="Quant net z = 0.7. Momentum + value carry.",
        evidence=[Evidence(kind="factor", ref="quant.momentum")],
        expires_at=when + timedelta(days=21),
    )
    fundamental = PlanV1(
        id=str(ulid.ULID()),
        team="fundamental",
        persona_slug=None,
        issued_at=when,
        asset=asset,
        action="buy",
        entry_price=100.0,
        entry_window_open=when,
        entry_window_close=when + timedelta(days=2),
        target_price=130.0,
        stop_loss=80.0,
        max_drawdown_pct=12.0,
        horizon_days=180,
        sizing_pct_nav=3.5,
        confidence=0.70,
        thesis="10-Q margin of safety to fair value $130.",
        evidence=[Evidence(kind="filing", ref="filing.AAPL_10Q_2026Q1")],
        expires_at=when + timedelta(days=180),
    )
    persona = PlanV1(
        id=str(ulid.ULID()),
        team="persona",
        persona_slug="consensus",
        issued_at=when,
        asset=asset,
        action="hold",
        entry_price=100.0,
        entry_window_open=when,
        entry_window_close=when + timedelta(hours=24),
        target_price=100.0,
        stop_loss=100.0,
        max_drawdown_pct=15.0,
        horizon_days=30,
        sizing_pct_nav=0.0,
        confidence=0.30,
        thesis="Persona panel split — flat.",
        evidence=[],
        disclaimer="Not advice; persona consensus rollup.",
        expires_at=when + timedelta(days=30),
    )

    decision = {
        "schema": "board.decision.v1",
        "id": str(ulid.ULID()),
        "trigger_event_id": "evt_001",
        "considered_plan_ids": [quant.id, fundamental.id, persona.id],
        "chosen_plan_id": fundamental.id,
        "chair_rationale": "Fundamental thesis dominates on horizon.",
        "dissent_record": (
            f"Quant ([{quant.id}]) wanted shorter horizon; "
            f"persona ([{persona.id}]) preferred hold."
        ),
        "risk_view": "(populated below)",
        "confidence": 0.72,
        "issued_at": when.isoformat(),
    }
    return decision, [quant, fundamental, persona]


def test_trading_room_brief_matches_golden_layout() -> None:
    decision, plans = _build_fixture()
    md = compose_trading_room_brief(
        decision=decision,
        considered_plans=plans,
        aggressive_view="Aggressive: full size.",
        conservative_view="Conservative: 1.5%.",
        neutral_view="Neutral: 3% — split the difference.",
    )
    # Substitute concrete plan ids → golden placeholders so the snapshot
    # is stable across ULID generation.
    chosen_id = decision["chosen_plan_id"]
    quant_id = decision["considered_plan_ids"][0]
    persona_id = decision["considered_plan_ids"][2]
    md_normalised = _normalize(
        md.replace(quant_id, "PLAN_QUANT")
        .replace(persona_id, "PLAN_PERSONA")
        .replace(chosen_id, "PLAN_FUND")
    )
    golden_normalised = _normalize(GOLDEN.read_text())
    assert md_normalised == golden_normalised


def test_trading_room_brief_handles_unknown_plan_gracefully() -> None:
    decision, plans = _build_fixture()
    # Choose a plan id that doesn't exist in the considered list.
    decision = {**decision, "chosen_plan_id": "01ZZZZZZZZZZZZZZZZZZZZZZZZ"}
    md = compose_trading_room_brief(decision=decision, considered_plans=plans)
    assert "unknown ticker" in md
    assert "Disclaimer" in md

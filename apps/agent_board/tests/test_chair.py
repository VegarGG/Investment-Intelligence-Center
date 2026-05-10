"""v2.5 N3.3 / T2.4 — Board Chair LLM synthesizer."""

from __future__ import annotations

import json

import pytest
from board.bull_bear import BullBearTranscript, DebateTurn
from board.chair import synthesize_decision
from board.risk_panel import RiskTranscript, RiskTurn
from schema.plan import PlanV1


def _bb(degraded: bool = False) -> BullBearTranscript:
    return BullBearTranscript(
        turns=[
            DebateTurn(side="bull", round_no=1, text="Bull", cost_skipped=degraded),
            DebateTurn(side="bear", round_no=1, text="Bear"),
        ],
        bull_summary="Bull thesis",
        bear_summary="Bear thesis",
        cost_skipped=degraded,
    )


def _risk() -> RiskTranscript:
    return RiskTranscript(
        turns=[
            RiskTurn(perspective="aggressive", text="A"),
            RiskTurn(perspective="conservative", text="C"),
            RiskTurn(perspective="neutral", text="N"),
        ],
        aggressive="A",
        conservative="C",
        neutral="N",
        cost_skipped=False,
    )


@pytest.mark.asyncio
async def test_chair_picks_a_valid_plan_and_returns_decision(
    sample_plans: list[PlanV1], stub_router
) -> None:
    chosen_id = sample_plans[1].id  # the fundamental plan
    stub_router.responses = {
        "board.chair": json.dumps(
            {
                "chosen_plan_id": chosen_id,
                "chair_rationale": "Higher conviction + longer horizon.",
                "dissent_record": (
                    f"Quant ([{sample_plans[0].id}]) and persona "
                    f"([{sample_plans[2].id}]) wanted hold."
                ),
                "risk_view": "Aggressive: ok at 3%; Conservative: trim.",
                "confidence": 0.72,
            }
        )
    }
    decision = await synthesize_decision(
        trigger_event_id="evt_001",
        plans=sample_plans,
        bull_bear=_bb(),
        risk=_risk(),
    )
    assert decision.chosen_plan_id == chosen_id
    assert decision.confidence == 0.72
    assert decision.dissent_record


@pytest.mark.asyncio
async def test_chair_falls_back_when_bull_bear_degraded(
    sample_plans: list[PlanV1], stub_router
) -> None:
    decision = await synthesize_decision(
        trigger_event_id="evt_002",
        plans=sample_plans,
        bull_bear=_bb(degraded=True),
        risk=_risk(),
    )
    # Falls back to highest-confidence plan deterministically.
    expected = max(sample_plans, key=lambda p: p.confidence)
    assert decision.chosen_plan_id == expected.id
    assert "Fallback" in decision.chair_rationale


@pytest.mark.asyncio
async def test_chair_falls_back_when_chair_picks_unknown_plan(
    sample_plans: list[PlanV1], stub_router
) -> None:
    stub_router.responses = {
        "board.chair": json.dumps(
            {
                "chosen_plan_id": "01ABCDEFGHJKMNPQRSTVWXYZ12",  # not in plans
                "chair_rationale": "...",
                "dissent_record": "...",
                "risk_view": "...",
                "confidence": 0.5,
            }
        )
    }
    decision = await synthesize_decision(
        trigger_event_id="evt_003",
        plans=sample_plans,
        bull_bear=_bb(),
        risk=_risk(),
    )
    assert decision.chosen_plan_id in {p.id for p in sample_plans}
    assert "Fallback" in decision.chair_rationale


@pytest.mark.asyncio
async def test_chair_falls_back_on_unparseable_json(
    sample_plans: list[PlanV1], stub_router
) -> None:
    stub_router.responses = {"board.chair": "not json at all, just prose"}
    decision = await synthesize_decision(
        trigger_event_id="evt_004",
        plans=sample_plans,
        bull_bear=_bb(),
        risk=_risk(),
    )
    assert decision.chosen_plan_id in {p.id for p in sample_plans}
    assert "Fallback" in decision.chair_rationale


@pytest.mark.asyncio
async def test_chair_raises_on_no_plans(stub_router) -> None:
    with pytest.raises(ValueError):
        await synthesize_decision(
            trigger_event_id="evt_x",
            plans=[],
            bull_bear=_bb(),
            risk=_risk(),
        )

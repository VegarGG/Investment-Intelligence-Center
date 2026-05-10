"""v2.5 N3.3 / T2.4 — Investment Board end-to-end."""

from __future__ import annotations

import json

import pytest
from board.bull_bear import debate
from board.chair import synthesize_decision
from board.persist import board_decision_to_advice
from board.risk_panel import deliberate
from board.schema import BoardDecisionV1
from schema.advice import AdviceV1
from schema.plan import PlanV1


@pytest.mark.asyncio
async def test_board_e2e_emits_one_decision_with_chosen_in_considered(
    sample_plans: list[PlanV1], stub_router
) -> None:
    chosen_id = sample_plans[1].id
    stub_router.responses = {
        "board.bull": "Bull: buy the fundamental thesis at $130 fair value.",
        "board.bear": "Bear: macro headwinds; size down.",
        "board.risk_aggressive": "Aggressive: full size.",
        "board.risk_conservative": "Conservative: 1.5%.",
        "board.risk_neutral": "Neutral: 3% — split the difference.",
        "board.chair": json.dumps(
            {
                "chosen_plan_id": chosen_id,
                "chair_rationale": "Fundamental thesis dominates on horizon.",
                "dissent_record": (
                    f"Quant ({sample_plans[0].id}) wanted shorter horizon; "
                    f"persona ({sample_plans[2].id}) preferred hold."
                ),
                "risk_view": "Aggressive 5% vs Conservative 1.5%; Chair adopts 3%.",
                "confidence": 0.72,
            }
        ),
    }

    bull_bear = await debate(sample_plans)
    risk = await deliberate(sample_plans)
    decision = await synthesize_decision(
        trigger_event_id="evt_e2e_001",
        plans=sample_plans,
        bull_bear=bull_bear,
        risk=risk,
    )

    assert isinstance(decision, BoardDecisionV1)
    assert decision.chosen_plan_id == chosen_id
    assert decision.chosen_plan_id in decision.considered_plan_ids
    # Dissent cites at least 2 of the considered plans by id.
    cited = sum(1 for pid in decision.considered_plan_ids if pid in decision.dissent_record)
    assert cited >= 2

    # Project to advice.v1 — schema-valid + chained on the lake.advice surface.
    advice = board_decision_to_advice(decision, sample_plans)
    assert isinstance(advice, AdviceV1)
    assert advice.agent == "board"
    assert advice.id == decision.id
    AdviceV1.model_validate(advice.model_dump(mode="json", by_alias=True))


@pytest.mark.asyncio
async def test_board_e2e_falls_back_when_bull_bear_returns_junk(
    sample_plans: list[PlanV1], stub_router
) -> None:
    """Bull/Bear breaker open → degraded; Chair picks deterministically."""
    stub_router.cost_skipped_callers = {"board.bull"}
    stub_router.responses = {
        "board.risk_aggressive": "...",
        "board.risk_conservative": "...",
        "board.risk_neutral": "...",
    }

    bull_bear = await debate(sample_plans)
    risk = await deliberate(sample_plans)
    decision = await synthesize_decision(
        trigger_event_id="evt_e2e_002",
        plans=sample_plans,
        bull_bear=bull_bear,
        risk=risk,
    )
    expected = max(sample_plans, key=lambda p: p.confidence)
    assert decision.chosen_plan_id == expected.id
    assert "Fallback" in decision.chair_rationale
    # Even on fallback, the projected advice still validates.
    advice = board_decision_to_advice(decision, sample_plans)
    AdviceV1.model_validate(advice.model_dump(mode="json", by_alias=True))


@pytest.mark.asyncio
async def test_board_decision_validators_reject_chosen_outside_considered() -> None:
    """Sanity: BoardDecisionV1's own validator catches a chosen-id mismatch."""
    import ulid
    from datetime import UTC, datetime

    with pytest.raises(ValueError):
        BoardDecisionV1(
            id=str(ulid.ULID()),
            trigger_event_id="evt_x",
            considered_plan_ids=["01ABCDEFGHJKMNPQRSTVWXYZ12"],
            chosen_plan_id="01ZZZZZZZZZZZZZZZZZZZZZZZZ",  # not in considered
            chair_rationale="r",
            dissent_record="d",
            risk_view="r",
            confidence=0.5,
            issued_at=datetime.now(UTC),
        )

"""v2.5 N3.3 / T2.4 — Bull/Bear debate sub-agent."""

from __future__ import annotations

import pytest
from board.bull_bear import MAX_ROUNDS, debate
from schema.plan import PlanV1


@pytest.mark.asyncio
async def test_debate_runs_max_rounds_when_router_healthy(
    sample_plans: list[PlanV1], stub_router
) -> None:
    stub_router.responses = {
        "board.bull": "Bull says buy on quant momentum.",
        "board.bear": "Bear says watch the regime risk.",
    }
    transcript = await debate(sample_plans)
    assert len(transcript.turns) == MAX_ROUNDS * 2
    assert transcript.bull_summary
    assert transcript.bear_summary
    assert transcript.degraded is False


@pytest.mark.asyncio
async def test_debate_breaks_early_when_cost_skipped(
    sample_plans: list[PlanV1], stub_router
) -> None:
    stub_router.responses = {"board.bull": "x", "board.bear": "y"}
    stub_router.cost_skipped_callers = {"board.bull"}
    transcript = await debate(sample_plans)
    # The first bull turn skipped → loop breaks before round 2 begins.
    assert transcript.degraded is True
    assert any(t.cost_skipped for t in transcript.turns)


@pytest.mark.asyncio
async def test_debate_raises_on_empty_plans(stub_router) -> None:
    with pytest.raises(ValueError):
        await debate([])

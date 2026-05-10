"""v2.5 N3.3 / T2.4 — 3-way Risk Panel sub-agent."""

from __future__ import annotations

import pytest
from board.risk_panel import MAX_TURNS, deliberate
from schema.plan import PlanV1


@pytest.mark.asyncio
async def test_three_perspectives_each_speak_once(
    sample_plans: list[PlanV1], stub_router
) -> None:
    stub_router.responses = {
        "board.risk_aggressive": "Size up to 5%.",
        "board.risk_conservative": "Size to 1.5%.",
        "board.risk_neutral": "Mid: 3%.",
    }
    transcript = await deliberate(sample_plans)
    perspectives = [t.perspective for t in transcript.turns]
    assert perspectives == ["aggressive", "conservative", "neutral"]
    assert len(transcript.turns) == MAX_TURNS
    assert transcript.aggressive
    assert transcript.conservative
    assert transcript.neutral


@pytest.mark.asyncio
async def test_risk_panel_breaks_when_cost_skipped(
    sample_plans: list[PlanV1], stub_router
) -> None:
    stub_router.responses = {"board.risk_aggressive": "x"}
    stub_router.cost_skipped_callers = {"board.risk_conservative"}
    transcript = await deliberate(sample_plans)
    assert transcript.degraded is True


@pytest.mark.asyncio
async def test_risk_panel_raises_on_empty_plans(stub_router) -> None:
    with pytest.raises(ValueError):
        await deliberate([])

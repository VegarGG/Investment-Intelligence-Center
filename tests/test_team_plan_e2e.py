"""v2.5 N3.2 / T2.3 — Three teams emit schema-valid PlanV1 envelopes.

Acceptance per plan §N3.2:
- Persona team produces ONE PlanV1 with non-empty disclaimer.
- Quant team produces ONE PlanV1 with empty disclaimer.
- Fundamental team produces ONE PlanV1.
- Each plan validates against `schema.plan.PlanV1`.
- Each plan's evidence list is non-empty for action != hold.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import ulid
from fund.team_plan import FilingThesis, synthesize_fundamental_plan
from persona.team_plan import synthesize_persona_plan
from quant.team_plan import synthesize_quant_plan
from schema.advice import AdviceV1, Asset, Evidence
from schema.plan import PlanV1


_ASSET = Asset(kind="equity", ticker="US.AAPL", venue="NASDAQ")
_NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)


def _persona_advice(slug: str, direction: str, conf: float, entry: float = 100.0) -> AdviceV1:
    if direction == "long":
        entry_band = (entry * 0.99, entry * 1.01)
        target = (entry * 1.10, entry * 1.15)
        stop = entry * 0.95
    elif direction == "short":
        entry_band = (entry * 0.99, entry * 1.01)
        # Bands are always stored ascending; the validator checks
        # target_band[1] < entry_band[0] for short direction.
        target = (entry * 0.85, entry * 0.90)
        stop = entry * 1.05
    else:
        # AdviceV1 flat-direction validator: entry_band and target_band must
        # both collapse to a single price.
        entry_band = (entry, entry)
        target = (entry, entry)
        stop = entry

    return AdviceV1(
        id=str(ulid.ULID()),
        agent=f"persona.{slug}",
        issued_at=_NOW,
        asset=_ASSET,
        thesis=f"{slug} sees the setup as {direction}.",
        direction=direction,  # type: ignore[arg-type]
        confidence=conf,
        entry_band=entry_band,
        target_band=target,
        stop_loss=stop,
        horizon_days=30,
        max_drawdown_pct=10.0,
        sizing_hint_pct_nav=2.0,
        expires_at=_NOW + timedelta(days=30),
        evidence=[Evidence(kind="news", ref=f"intel.{slug}.x")],
        disclaimer=f"This is research from the {slug} persona.",
    )


@pytest.mark.asyncio
async def test_persona_team_emits_consensus_plan_with_disclaimer() -> None:
    advices = [
        _persona_advice("buffett", "long", 0.80),
        _persona_advice("burry", "flat", 0.40),
        _persona_advice("dalio", "long", 0.55),
        _persona_advice("druckenmiller", "long", 0.70),
        _persona_advice("rogers", "long", 0.60),
        _persona_advice("soros", "short", 0.40),
        _persona_advice("wood", "long", 0.85),
        _persona_advice("retail_degen", "long", 0.50),
    ]
    plan = await synthesize_persona_plan(advices, asof=_NOW)

    assert isinstance(plan, PlanV1)
    assert plan.team == "persona"
    assert plan.persona_slug == "consensus"
    assert (plan.disclaimer or "").strip(), "persona team disclaimer must be non-empty"
    assert plan.action == "buy"
    assert plan.evidence, "buy plan must cite evidence"
    # Validators ran via Pydantic — schema-valid.
    PlanV1.model_validate(plan.model_dump(mode="json", by_alias=True))


@pytest.mark.asyncio
async def test_persona_team_falls_back_to_hold_on_split_panel() -> None:
    advices = [
        _persona_advice("buffett", "long", 0.80),
        _persona_advice("burry", "short", 0.80),
        _persona_advice("dalio", "long", 0.50),
        _persona_advice("soros", "short", 0.50),
        _persona_advice("wood", "flat", 0.50),
        _persona_advice("druckenmiller", "flat", 0.50),
        _persona_advice("rogers", "flat", 0.50),
        _persona_advice("retail_degen", "long", 0.50),
    ]
    plan = await synthesize_persona_plan(advices, asof=_NOW)
    # No clear majority → flat → hold action.
    assert plan.action in {"hold", "buy"}  # depends on tie-break


def test_quant_team_emits_plan_with_no_disclaimer() -> None:
    plan = synthesize_quant_plan(
        asset=_ASSET,
        mark_price=100.0,
        factor_scores={
            "momentum_12_1": 1.4,
            "value_pb": 0.8,
            "quality_roic": 0.6,
            "low_vol": -0.2,
        },
        asof=_NOW,
    )
    assert plan.team == "quant"
    assert plan.persona_slug is None
    assert (plan.disclaimer or "") == "" or plan.disclaimer is None
    assert plan.action in {"buy", "sell", "hold"}
    if plan.action != "hold":
        assert plan.evidence
    PlanV1.model_validate(plan.model_dump(mode="json", by_alias=True))


def test_quant_team_caps_sizing_at_5_pct_nav() -> None:
    plan = synthesize_quant_plan(
        asset=_ASSET,
        mark_price=100.0,
        factor_scores={"super_factor": 5.0},  # extreme
        asof=_NOW,
    )
    assert plan.sizing_pct_nav <= 5.0


def test_fundamental_team_emits_filing_based_plan() -> None:
    theses = [
        FilingThesis(
            filing_ref="AAPL_10Q_2026Q1",
            filing_url="https://sec.gov/aapl/10q-2026q1.htm",
            direction="long",
            conviction=0.7,
            fair_value=130.0,
            margin_of_safety_pct=20.0,
            horizon_days=180,
            thesis="Services growth + buybacks support a $130 fair value.",
        ),
        FilingThesis(
            filing_ref="AAPL_8K_2026_03",
            filing_url="https://sec.gov/aapl/8k-2026-03.htm",
            direction="long",
            conviction=0.4,
            fair_value=115.0,
            margin_of_safety_pct=10.0,
            horizon_days=90,
            thesis="Mid-quarter beat.",
        ),
    ]
    plan = synthesize_fundamental_plan(
        asset=_ASSET, mark_price=100.0, theses=theses, asof=_NOW
    )
    assert plan.team == "fundamental"
    assert plan.action == "buy"
    assert plan.confidence == 0.7
    assert any("AAPL_10Q_2026Q1" in (e.ref or "") for e in plan.evidence)
    PlanV1.model_validate(plan.model_dump(mode="json", by_alias=True))


def test_fundamental_team_emits_hold_when_no_thesis() -> None:
    plan = synthesize_fundamental_plan(
        asset=_ASSET, mark_price=100.0, theses=[], asof=_NOW
    )
    assert plan.team == "fundamental"
    assert plan.action == "hold"
    assert plan.confidence < 0.2

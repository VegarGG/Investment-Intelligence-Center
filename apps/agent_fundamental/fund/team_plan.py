"""Fundamental team writer (v2.5 N3.2 / T2.3).

Picks the highest-conviction filing-based thesis from the watchlist for
the requested ticker and emits ONE ``PlanV1`` with ``team='fundamental'``.

Conviction is the input-side ``conviction`` score (0..1) emitted by the
fundamental valuation pipeline (workflow 12 §5). When no filing thesis
exists yet, the writer returns a hold plan citing the most recent
filing as the reason for caution.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import ulid
from schema.advice import Asset, Evidence
from schema.plan import PlanV1, PortfolioContextV1


@dataclass(frozen=True, slots=True)
class FilingThesis:
    """One candidate thesis the fundamental analyst pipeline produced.

    Pure data; the writer below picks the winner and shapes a PlanV1.
    """

    filing_ref: str
    filing_url: str
    direction: str  # 'long' | 'short' | 'flat'
    conviction: float
    fair_value: float
    margin_of_safety_pct: float
    horizon_days: int
    thesis: str


def _direction_to_action(direction: str) -> str:
    if direction == "long":
        return "buy"
    if direction == "short":
        return "sell"
    return "hold"


def _winner(theses: Sequence[FilingThesis]) -> FilingThesis | None:
    if not theses:
        return None
    return max(theses, key=lambda t: t.conviction)


def synthesize_fundamental_plan(
    *,
    asset: Asset,
    mark_price: float,
    theses: Sequence[FilingThesis],
    portfolio_context: PortfolioContextV1 | None = None,
    asof: datetime | None = None,
) -> PlanV1:
    when = asof or datetime.now(UTC)
    px = max(mark_price, 1e-6)

    winner = _winner(theses)
    if winner is None or winner.conviction < 0.2:
        # No conviction → hold.
        return PlanV1(
            id=str(ulid.ULID()),
            team="fundamental",
            persona_slug=None,
            issued_at=when,
            asset=asset,
            action="hold",
            entry_price=px,
            entry_window_open=when,
            entry_window_close=when + timedelta(hours=24),
            target_price=px,
            stop_loss=px,
            max_drawdown_pct=8.0,
            horizon_days=180,
            sizing_pct_nav=0.0,
            confidence=0.1,
            thesis="No high-conviction filing-based thesis available; standing flat.",
            evidence=[],
            portfolio_context=portfolio_context,
            expires_at=when + timedelta(days=180),
            disclaimer=None,
        )

    action = _direction_to_action(winner.direction)
    fair_value = max(winner.fair_value, 1e-6)
    mos = winner.margin_of_safety_pct / 100.0

    if action == "buy":
        entry_price = px
        target_price = max(fair_value, px * (1.0 + max(mos, 0.05)))
        stop_loss = px * (1.0 - max(mos, 0.05))
    elif action == "sell":
        entry_price = px
        target_price = min(fair_value, px * (1.0 - max(mos, 0.05)))
        stop_loss = px * (1.0 + max(mos, 0.05))
    else:
        entry_price = px
        target_price = px
        stop_loss = px

    return PlanV1(
        id=str(ulid.ULID()),
        team="fundamental",
        persona_slug=None,
        issued_at=when,
        asset=asset,
        action=action,  # type: ignore[arg-type]
        entry_price=entry_price,
        entry_window_open=when,
        entry_window_close=when + timedelta(days=2),
        target_price=target_price,
        stop_loss=stop_loss,
        max_drawdown_pct=12.0,
        horizon_days=winner.horizon_days,
        sizing_pct_nav=min(5.0, winner.conviction * 5.0),
        confidence=winner.conviction,
        thesis=winner.thesis,
        evidence=[
            Evidence(kind="filing", ref=winner.filing_ref, url=winner.filing_url),
        ],
        portfolio_context=portfolio_context,
        expires_at=when + timedelta(days=winner.horizon_days),
        disclaimer=None,
    )


async def team_plan_endpoint_payload(request: dict[str, Any]) -> dict[str, Any]:
    asset = Asset.model_validate(request["asset"])
    mark_price = float(request.get("mark_price", 0.0))
    theses = [
        FilingThesis(
            filing_ref=str(t["filing_ref"]),
            filing_url=str(t["filing_url"]),
            direction=str(t.get("direction", "flat")),
            conviction=float(t.get("conviction", 0.0)),
            fair_value=float(t.get("fair_value", mark_price)),
            margin_of_safety_pct=float(t.get("margin_of_safety_pct", 0.0)),
            horizon_days=int(t.get("horizon_days", 90)),
            thesis=str(t.get("thesis", "")),
        )
        for t in request.get("theses") or []
    ]
    pc_raw = request.get("portfolio_context")
    pc = PortfolioContextV1.model_validate(pc_raw) if pc_raw else None
    plan = synthesize_fundamental_plan(
        asset=asset,
        mark_price=mark_price,
        theses=theses,
        portfolio_context=pc,
    )
    return plan.model_dump(mode="json", by_alias=True)

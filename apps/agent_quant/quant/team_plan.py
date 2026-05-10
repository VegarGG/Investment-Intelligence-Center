"""Quant team writer (v2.5 N3.2 / T2.3).

Aggregates the 8-factor library's z-scores into ONE ``PlanV1`` per
ticker per trigger event. ``team='quant'``; no LLM cost path
(deterministic numeric synthesis).

Synthesis rules:
  - net_z = sum of factor weights × per-factor z-scores
  - action = sign(net_z)            ('buy' if > 0.5; 'sell' if < -0.5; else 'hold')
  - confidence = clipped sigmoid of |net_z|
  - sizing = clipped at 5% NAV
  - entry/target/stop derive from the live mark + |net_z|-driven bands
  - evidence cites each non-zero factor by name
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import ulid
from schema.advice import Asset, Evidence
from schema.plan import PlanV1, PortfolioContextV1


MAX_SIZING_PCT_NAV = 5.0


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _net_z(factor_scores: Mapping[str, float], weights: Mapping[str, float] | None = None) -> float:
    if not factor_scores:
        return 0.0
    if weights is None:
        return statistics.fmean(factor_scores.values())
    total_w = sum(abs(w) for w in weights.values()) or 1.0
    return sum(factor_scores.get(k, 0.0) * w for k, w in weights.items()) / total_w


def _action_for(net_z: float) -> tuple[str, str]:
    if net_z > 0.5:
        return "buy", "long"
    if net_z < -0.5:
        return "sell", "short"
    return "hold", "flat"


def synthesize_quant_plan(
    *,
    asset: Asset,
    mark_price: float,
    factor_scores: Mapping[str, float],
    factor_weights: Mapping[str, float] | None = None,
    portfolio_context: PortfolioContextV1 | None = None,
    asof: datetime | None = None,
    horizon_days: int = 21,
) -> PlanV1:
    """Build one ``PlanV1`` from a dict of factor → z-score.

    Empty `factor_scores` yields a hold plan with confidence 0.0 — the
    caller should usually short-circuit before calling, but we don't fail.
    """

    when = asof or datetime.now(UTC)
    px = max(mark_price, 1e-6)
    net_z = _net_z(factor_scores, factor_weights)
    action, _direction = _action_for(net_z)

    band_pct = min(0.10, max(0.01, abs(net_z) * 0.05))  # 1–10% band

    if action == "buy":
        entry_price = px
        target_price = px * (1.0 + band_pct * 2.0)
        stop_loss = px * (1.0 - band_pct)
    elif action == "sell":
        entry_price = px
        target_price = px * (1.0 - band_pct * 2.0)
        stop_loss = px * (1.0 + band_pct)
    else:
        # hold — mark-to-mark, no movement; PlanV1 allows this.
        entry_price = px
        target_price = px
        stop_loss = px

    confidence = max(0.0, min(1.0, abs(_sigmoid(net_z) - 0.5) * 2.0))
    sizing = min(MAX_SIZING_PCT_NAV, abs(net_z) * 2.0)

    evidence: list[Evidence] = []
    if action != "hold":
        for name, z in factor_scores.items():
            if abs(z) < 1e-3:
                continue
            evidence.append(
                Evidence(kind="factor", ref=f"quant.factor.{name}@z={z:+.2f}")
            )
        if not evidence:
            evidence = [Evidence(kind="factor", ref=f"quant.factor.net_z@{net_z:+.2f}")]

    thesis = (
        f"Quant net z-score = {net_z:+.2f} (action={action}). "
        f"Driving factors: "
        + ", ".join(
            f"{name}({z:+.2f})"
            for name, z in sorted(factor_scores.items(), key=lambda kv: -abs(kv[1]))[:5]
        )
        + ". Sizing capped at 5% NAV."
    )

    return PlanV1(
        id=str(ulid.ULID()),
        team="quant",
        persona_slug=None,
        issued_at=when,
        asset=asset,
        action=action,  # type: ignore[arg-type]
        entry_price=entry_price,
        entry_window_open=when,
        entry_window_close=when + timedelta(hours=8),
        target_price=target_price,
        stop_loss=stop_loss,
        max_drawdown_pct=10.0,
        horizon_days=horizon_days,
        sizing_pct_nav=sizing,
        confidence=confidence,
        thesis=thesis,
        evidence=evidence,
        portfolio_context=portfolio_context,
        expires_at=when + timedelta(days=horizon_days),
        disclaimer=None,  # quant team is not subject to the persona-disclaimer rule
    )


async def team_plan_endpoint_payload(request: dict[str, Any]) -> dict[str, Any]:
    asset = Asset.model_validate(request["asset"])
    mark_price = float(request.get("mark_price", 0.0))
    factor_scores = dict(request.get("factor_scores") or {})
    factor_weights = request.get("factor_weights")
    pc_raw = request.get("portfolio_context")
    pc = PortfolioContextV1.model_validate(pc_raw) if pc_raw else None
    horizon_days = int(request.get("horizon_days", 21))

    plan = synthesize_quant_plan(
        asset=asset,
        mark_price=mark_price,
        factor_scores=factor_scores,
        factor_weights=factor_weights,
        portfolio_context=pc,
        horizon_days=horizon_days,
    )
    return plan.model_dump(mode="json", by_alias=True)

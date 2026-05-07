"""Composes advice.quant.v1 (workflow 12 §5.5)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import ulid
from llm_client import ChatMessage, chat
from schema import AdviceV1, Asset, Evidence

from .risk import SizedTrade

HORIZON_DEFAULTS = {
    "momentum": 30,
    "mean_reversion": 5,
    "vol_risk_premium": 14,
    "pead": 10,
    "insider": 30,
    "sector_rs": 21,
}


async def compose(
    trade: SizedTrade,
    *,
    regime: str,
    asof: datetime | None = None,
    asof_factor_matrix: str = "lake.factor_matrix",
) -> AdviceV1:
    when = asof or datetime.now(UTC)
    primary_factor = trade.candidate.contributing_factors[:1] or ("unknown",)
    secondary_factor = trade.candidate.contributing_factors[1:2] or ("unknown",)
    horizon = HORIZON_DEFAULTS.get(primary_factor[0], 21)

    response = await chat(
        caller_id="quant.writer",
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "In ≤ 60 words, narrate why this factor combo flagged this ticker. "
                    "State the dominant factor, the secondary factor, the regime context, "
                    "and the time horizon. No hedging."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"ticker={trade.candidate.ticker} "
                    f"direction={trade.candidate.direction} "
                    f"primary={primary_factor[0]} "
                    f"secondary={secondary_factor[0]} "
                    f"regime={regime} "
                    f"horizon_days={horizon}"
                ),
            ),
        ],
        max_tokens=200,
        temperature=0.2,
    )
    thesis = response.text.strip()

    confidence = _sigmoid_confidence(trade.candidate.combined_z)
    evidence = [
        Evidence(
            kind="factor",
            ref=(
                f"{asof_factor_matrix}:asof={when.date().isoformat()},"
                f"ticker={trade.candidate.ticker}"
            ),
        ),
    ]
    return AdviceV1(
        id=str(ulid.ULID()),
        agent="quant",
        issued_at=when,
        asset=Asset(kind="equity", ticker=trade.candidate.ticker, venue=trade.candidate.venue),
        thesis=thesis,
        direction=trade.candidate.direction,
        confidence=confidence,
        entry_band=trade.entry_band,
        target_band=trade.target_band,
        stop_loss=trade.stop_loss,
        horizon_days=horizon,
        max_drawdown_pct=10.0,
        sizing_hint_pct_nav=trade.weight_pct_nav,
        expires_at=when + timedelta(days=horizon),
        evidence=evidence,
    )


def _sigmoid_confidence(z: float) -> float:
    return max(0.05, min(0.95, 1.0 / (1.0 + math.exp(-z))))

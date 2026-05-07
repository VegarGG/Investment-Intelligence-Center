"""Risk shaping (workflow 12 §2.4 + §5.4).

Vol-target sizing, correlation cap, sector cap, region cap. The QP is
intentionally a heuristic: greedy reject when caps would be violated.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .types import Candidate

VOL_TARGET = 0.12
PER_POSITION_MAX_PCT = 5.0
SECTOR_CAP_PCT = 25.0
REGION_CAP_PCT = 50.0
CORRELATION_CAP = 0.85
LIQUIDITY_RATIO_MIN = 10.0  # 5-day median dollar volume vs trade value


@dataclass(slots=True)
class SizedTrade:
    candidate: Candidate
    weight_pct_nav: float
    entry_band: tuple[float, float]
    target_band: tuple[float, float]
    stop_loss: float


def shape(
    candidates: list[Candidate],
    *,
    nav_usd: float,
    correlations: Mapping[tuple[str, str], float] | None = None,
    atr_pct_by_ticker: Mapping[str, float] | None = None,
) -> list[SizedTrade]:
    """Apply vol target, correlation cap, sector cap, region cap, liquidity."""
    correlations = correlations or {}
    atr_pct_by_ticker = atr_pct_by_ticker or {}
    accepted: list[SizedTrade] = []
    sector_used: dict[str, float] = {}
    region_used: dict[str, float] = {}

    for c in sorted(candidates, key=lambda c: -abs(c.combined_z)):
        weight = _vol_target_weight(c)
        if weight <= 0:
            continue
        weight = min(weight, PER_POSITION_MAX_PCT)
        if not _passes_liquidity(c, nav_usd, weight):
            continue
        if not _passes_correlation(c, accepted, correlations):
            continue
        if sector_used.get(c.sector, 0.0) + weight > SECTOR_CAP_PCT:
            continue
        if region_used.get(c.region, 0.0) + weight > REGION_CAP_PCT:
            continue
        sector_used[c.sector] = sector_used.get(c.sector, 0.0) + weight
        region_used[c.region] = region_used.get(c.region, 0.0) + weight
        accepted.append(_with_bands(c, weight, atr_pct_by_ticker))
    return accepted


def _vol_target_weight(c: Candidate) -> float:
    if c.realized_vol_60d <= 0:
        return 0.0
    return (VOL_TARGET / c.realized_vol_60d) * 100.0 / 10.0  # ~portfolio leverage cap


def _passes_liquidity(c: Candidate, nav: float, weight_pct: float) -> bool:
    if c.median_dollar_volume_5d <= 0:
        return True  # caller didn't supply — don't block
    trade_value = nav * (weight_pct / 100.0)
    return c.median_dollar_volume_5d >= trade_value * LIQUIDITY_RATIO_MIN


def _passes_correlation(
    c: Candidate, accepted: list[SizedTrade], correlations: Mapping[tuple[str, str], float]
) -> bool:
    for prior in accepted:
        key = tuple(sorted([c.ticker, prior.candidate.ticker]))
        rho = correlations.get((key[0], key[1]), 0.0)
        if abs(rho) > CORRELATION_CAP:
            return False
    return True


def _with_bands(
    c: Candidate, weight_pct: float, atr_pct_by_ticker: Mapping[str, float]
) -> SizedTrade:
    atr_pct = atr_pct_by_ticker.get(c.ticker, 0.02)
    px = max(c.last_close, 1e-6)
    if c.direction == "long":
        entry = (px * (1 - 0.5 * atr_pct), px * (1 + 0.5 * atr_pct))
        target = (px * (1 + 1.5 * atr_pct), px * (1 + 2.5 * atr_pct))
        stop = px * (1 - 1.2 * atr_pct)
    else:
        entry = (px * (1 - 0.5 * atr_pct), px * (1 + 0.5 * atr_pct))
        target = (px * (1 - 2.5 * atr_pct), px * (1 - 1.5 * atr_pct))
        stop = px * (1 + 1.2 * atr_pct)
    return SizedTrade(
        candidate=c,
        weight_pct_nav=weight_pct,
        entry_band=entry,
        target_band=target,
        stop_loss=stop,
    )

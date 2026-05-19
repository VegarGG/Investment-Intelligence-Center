"""Regime detector (P7.5).

Classifies the market into one of:
    risk_on | risk_off | rate_cut | stagflation | recession | crisis | unknown

Inputs (all optional; missing inputs → `unknown`):
  - VIX EMA over 20 trading days
  - cross-sectional breadth (% of universe above 50-day MA)
  - correlation cluster (mean pairwise correlation over universe)
  - 10y - 2y yield spread (basis points)

The thresholds match the v2.5 §12 §2.4 regime decision table; tune by
backtest, not by guess. Anything outside the matrix → `unknown` (the
safe default that disables every regime-conditional factor weight).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Regime = Literal[
    "risk_on", "risk_off", "rate_cut", "stagflation", "recession", "crisis", "unknown"
]


@dataclass(frozen=True, slots=True)
class RegimeInputs:
    vix_ema_20d: float | None = None
    breadth_pct: float | None = None  # % above 50d MA, [0, 1]
    pairwise_corr: float | None = None  # mean correlation, [-1, 1]
    yield_curve_bps: float | None = None  # 10y - 2y, basis points


def classify(inputs: RegimeInputs) -> Regime:
    vix = inputs.vix_ema_20d
    breadth = inputs.breadth_pct
    corr = inputs.pairwise_corr
    curve = inputs.yield_curve_bps

    if vix is None:
        return "unknown"

    # CRISIS: VIX > 35 with high correlation (everything moves together).
    if vix > 35 and (corr is None or corr > 0.6):
        return "crisis"

    # RISK_OFF: elevated VIX, breadth deteriorating.
    if vix > 25 and (breadth is None or breadth < 0.45):
        return "risk_off"

    # RECESSION: curve inverted by > 30 bps + breadth weak.
    if curve is not None and curve < -30 and (breadth is None or breadth < 0.5):
        return "recession"

    # STAGFLATION: high VIX with curve still inverted but breadth not collapsing.
    if vix > 22 and curve is not None and curve < 0:
        return "stagflation"

    # RATE_CUT regime: low VIX + flat/inverted curve (market expecting cuts).
    if vix < 18 and curve is not None and curve < 10:
        return "rate_cut"

    # RISK_ON: low VIX + healthy breadth.
    if vix < 20 and (breadth is None or breadth > 0.55):
        return "risk_on"

    return "unknown"

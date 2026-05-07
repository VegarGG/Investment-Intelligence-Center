"""Signal combination (workflow 12 §2.3, §5.3).

Reads `iic_state.macro_regime` and applies the §2.3 weight table to the
factor z-scores, producing a per-ticker combined score. Top-N longs +
bottom-N shorts become candidate trades.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from typing import Literal

from .types import Candidate, FactorRow

Regime = Literal["risk_on", "risk_off", "rate_cut", "stagflation", "recession", "crisis", "unknown"]

# GROUND TRUTH — workflow 12 §2.3 verbatim.
REGIME_WEIGHTS: dict[Regime, dict[str, float]] = {
    "risk_on": {
        "momentum": 0.30,
        "mean_reversion": 0.10,
        "vol_risk_premium": 0.15,
        "pead": 0.10,
        "insider": 0.05,
        "sector_rs": 0.20,
        "crypto_basis": 0.05,
        "fx_carry": 0.05,
    },
    "risk_off": {
        "momentum": 0.10,
        "mean_reversion": 0.20,
        "vol_risk_premium": 0.30,
        "pead": 0.05,
        "insider": 0.10,
        "sector_rs": 0.15,
        "crypto_basis": 0.00,
        "fx_carry": 0.10,
    },
    "rate_cut": {
        "momentum": 0.25,
        "mean_reversion": 0.15,
        "vol_risk_premium": 0.10,
        "pead": 0.10,
        "insider": 0.05,
        "sector_rs": 0.20,
        "crypto_basis": 0.05,
        "fx_carry": 0.10,
    },
    "stagflation": {
        "momentum": 0.05,
        "mean_reversion": 0.10,
        "vol_risk_premium": 0.20,
        "pead": 0.05,
        "insider": 0.10,
        "sector_rs": 0.10,
        "crypto_basis": 0.00,
        "fx_carry": 0.40,
    },
    "recession": {
        "momentum": 0.05,
        "mean_reversion": 0.30,
        "vol_risk_premium": 0.30,
        "pead": 0.10,
        "insider": 0.10,
        "sector_rs": 0.10,
        "crypto_basis": 0.00,
        "fx_carry": 0.05,
    },
    "crisis": {
        "momentum": 0.05,
        "mean_reversion": 0.20,
        "vol_risk_premium": 0.40,
        "pead": 0.05,
        "insider": 0.05,
        "sector_rs": 0.05,
        "crypto_basis": 0.00,
        "fx_carry": 0.20,
    },
    "unknown": {
        "momentum": 0.20,
        "mean_reversion": 0.15,
        "vol_risk_premium": 0.15,
        "pead": 0.10,
        "insider": 0.10,
        "sector_rs": 0.15,
        "crypto_basis": 0.05,
        "fx_carry": 0.10,
    },
}


def regime_weights(regime: Regime) -> dict[str, float]:
    """Public introspection helper (workflow 12 §7 dashboard surface)."""
    return dict(REGIME_WEIGHTS[regime])


def combine(
    factor_rows: Iterable[FactorRow],
    *,
    regime: Regime,
    candidates_meta: Mapping[str, Candidate],
    n_per_side: int = 10,
) -> list[Candidate]:
    """Sum weighted z-scores per ticker, then split top/bottom N."""
    weights = REGIME_WEIGHTS[regime]
    z_by_factor_ticker: dict[str, dict[str, float]] = {}
    for row in factor_rows:
        z_by_factor_ticker.setdefault(row.factor_id, {})[row.ticker] = row.value

    z_scores: dict[str, dict[str, float]] = {}
    for factor_id, by_ticker in z_by_factor_ticker.items():
        if not by_ticker:
            continue
        vals = list(by_ticker.values())
        mu = statistics.fmean(vals)
        sigma = statistics.pstdev(vals) if len(vals) > 1 else 1.0
        sigma = sigma or 1.0
        z_scores[factor_id] = {t: (v - mu) / sigma for t, v in by_ticker.items()}

    combined: dict[str, float] = {}
    contributors: dict[str, list[str]] = {}
    for factor_id, by_ticker in z_scores.items():
        w = weights.get(factor_id, 0.0)
        if w == 0.0:
            continue
        for ticker, z in by_ticker.items():
            combined[ticker] = combined.get(ticker, 0.0) + w * z
            if abs(w * z) > 0.05:
                contributors.setdefault(ticker, []).append(factor_id)

    ranked = sorted(combined.items(), key=lambda kv: kv[1], reverse=True)
    longs = ranked[:n_per_side]
    shorts = ranked[-n_per_side:]
    out: list[Candidate] = []
    for ticker, score in longs:
        meta = candidates_meta.get(ticker)
        if meta is None:
            continue
        out.append(
            _with_score(
                meta, direction="long", combined_z=score, contribs=contributors.get(ticker, [])
            )
        )
    for ticker, score in shorts:
        meta = candidates_meta.get(ticker)
        if meta is None:
            continue
        out.append(
            _with_score(
                meta, direction="short", combined_z=score, contribs=contributors.get(ticker, [])
            )
        )
    return out


def _with_score(
    base: Candidate,
    *,
    direction: Literal["long", "short"],
    combined_z: float,
    contribs: list[str],
) -> Candidate:
    return Candidate(
        ticker=base.ticker,
        venue=base.venue,
        region=base.region,
        sector=base.sector,
        direction=direction,
        combined_z=combined_z,
        contributing_factors=tuple(contribs),
        realized_vol_60d=base.realized_vol_60d,
        median_dollar_volume_5d=base.median_dollar_volume_5d,
        last_close=base.last_close,
    )

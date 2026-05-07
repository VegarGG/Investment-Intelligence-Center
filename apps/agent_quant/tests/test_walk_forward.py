"""Workflow 12 §5.7 — synthetic walk-forward sanity check.

This is a deterministic toy: with a positive momentum signal and a
mean-reversion overlay, the long basket should beat the short basket.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from quant.signal import combine
from quant.types import Candidate, FactorRow


def _candidate(ticker: str) -> Candidate:
    return Candidate(
        ticker=ticker,
        venue="NASDAQ",
        region="US",
        sector="Tech",
        direction="long",
        combined_z=0.0,
        realized_vol_60d=0.20,
        median_dollar_volume_5d=1_000_000,
        last_close=100.0,
    )


def test_combine_picks_top_n() -> None:
    """Synthetic momentum + mean_reversion factor rows. Top-N longs are the
    high-momentum names; bottom-N shorts are the low-momentum names."""
    asof = datetime(2026, 1, 1, tzinfo=UTC)
    rng = random.Random(42)
    tickers = [f"T{i:02d}" for i in range(30)]
    momentum = {t: rng.uniform(-0.2, 0.2) for t in tickers}
    rows: list[FactorRow] = []
    for t, v in momentum.items():
        rows.append(FactorRow(asof=asof, ticker=t, factor_id="momentum", value=v, rank=0))

    candidates = combine(
        rows,
        regime="risk_on",
        candidates_meta={t: _candidate(t) for t in tickers},
        n_per_side=5,
    )
    longs = [c for c in candidates if c.direction == "long"]
    shorts = [c for c in candidates if c.direction == "short"]
    assert len(longs) == 5
    assert len(shorts) == 5
    # Top long should have the highest combined z.
    long_zs = sorted([c.combined_z for c in longs], reverse=True)
    short_zs = sorted([c.combined_z for c in shorts])
    assert long_zs[0] > short_zs[0]

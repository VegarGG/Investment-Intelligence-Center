"""Workflow 12 §2.4 — risk caps reject violators."""

from __future__ import annotations

from quant.risk import shape
from quant.types import Candidate


def _cand(ticker: str, sector: str, region: str = "US") -> Candidate:
    return Candidate(
        ticker=ticker,
        venue="NASDAQ",
        region=region,  # type: ignore[arg-type]
        sector=sector,
        direction="long",
        combined_z=2.0,
        realized_vol_60d=0.20,
        median_dollar_volume_5d=10_000_000,
        last_close=100.0,
    )


def test_correlation_cap_rejects_correlated_pairs() -> None:
    cands = [_cand("A", "Tech"), _cand("B", "Tech")]
    correlations = {("A", "B"): 0.95}
    sized = shape(cands, nav_usd=1_000_000, correlations=correlations)
    tickers = {s.candidate.ticker for s in sized}
    assert len(tickers) == 1


def test_sector_cap_caps_exposure() -> None:
    cands = [_cand(f"T{i}", "Tech") for i in range(10)]
    sized = shape(cands, nav_usd=1_000_000)
    sector_total = sum(s.weight_pct_nav for s in sized)
    assert sector_total <= 25.0 + 1e-6


def test_region_cap_caps_exposure() -> None:
    cands = [_cand(f"T{i}", f"Sector{i}", region="US") for i in range(20)]
    sized = shape(cands, nav_usd=1_000_000)
    region_total = sum(s.weight_pct_nav for s in sized)
    assert region_total <= 50.0 + 1e-6


def test_per_position_max_5pct() -> None:
    cands = [_cand("X", "Tech")]
    sized = shape(cands, nav_usd=1_000_000)
    assert sized
    assert sized[0].weight_pct_nav <= 5.0 + 1e-6

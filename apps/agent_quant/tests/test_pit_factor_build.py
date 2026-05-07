"""Workflow 12 §5.1, §9 — PIT correctness for universe + momentum."""

from __future__ import annotations

from datetime import UTC, datetime

from quant.factors.momentum import momentum_12_1
from quant.types import Bar
from quant.universe import Membership, constituents


def _bars(ticker: str, n: int, *, start_close: float = 100.0) -> list[Bar]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(
            ticker=ticker,
            asof=base.replace(day=(i % 28) + 1, month=((i // 28) % 12) + 1),
            open=start_close + i,
            high=start_close + i + 1,
            low=start_close + i - 1,
            close=start_close + i,
            volume=1_000_000,
        )
        for i in range(n)
    ]


def test_universe_excludes_delisted() -> None:
    rows = [
        Membership("SPX", "AAPL", datetime(2020, 1, 1), None),
        Membership("SPX", "LEH", datetime(2000, 1, 1), datetime(2008, 9, 15)),
    ]
    asof_2026 = datetime(2026, 1, 1)
    asof_2008 = datetime(2008, 1, 1)
    assert "LEH" not in constituents(rows, "SPX", asof=asof_2026)
    assert "LEH" in constituents(rows, "SPX", asof=asof_2008)


def test_momentum_skips_recent_month() -> None:
    """12-1 should ignore the most recent ~1 month — adding a spike at the
    end must NOT change the factor value."""
    bars = _bars("AAA", 252)
    ref = momentum_12_1(bars, lookback_days=252)["AAA"]

    # Inject a huge spike in the last 21 bars (the skipped window).
    bars_with_spike = list(bars)
    for i in range(231, 252):
        bars_with_spike[i] = Bar(
            ticker="AAA",
            asof=bars_with_spike[i].asof,
            open=bars_with_spike[i].open,
            high=bars_with_spike[i].high,
            low=bars_with_spike[i].low,
            close=bars_with_spike[i].close * 10,
            volume=bars_with_spike[i].volume,
        )
    after_spike = momentum_12_1(bars_with_spike, lookback_days=252)["AAA"]
    assert after_spike == ref  # the spike fell inside the skipped window


def test_momentum_returns_empty_for_short_history() -> None:
    bars = _bars("AAA", 50)
    assert momentum_12_1(bars, lookback_days=252) == {}

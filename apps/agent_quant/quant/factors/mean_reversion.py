"""5-day post-news mean-reversion residual (workflow 12 §2.1 #2)."""

from __future__ import annotations

from collections.abc import Iterable

from ..types import Bar


def mean_reversion_5d(history: Iterable[Bar]) -> dict[str, float]:
    """Negative of the trailing 5-day return, normalized by stdev. Long
    losers, short winners — sign convention matches workflow 12 §5.4."""
    by_ticker: dict[str, list[Bar]] = {}
    for bar in history:
        by_ticker.setdefault(bar.ticker, []).append(bar)
    out: dict[str, float] = {}
    for ticker, bars in by_ticker.items():
        bars.sort(key=lambda b: b.asof)
        if len(bars) < 6:
            continue
        ret = bars[-1].close / bars[-6].close - 1.0
        out[ticker] = -ret
    return out

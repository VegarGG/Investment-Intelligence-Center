"""12-1 cross-sectional momentum (workflow 12 §2.1 #1).

Excludes the most recent month to avoid the well-documented short-term
reversal contamination.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..types import Bar


def momentum_12_1(history: Iterable[Bar], *, lookback_days: int = 252) -> dict[str, float]:
    """Return {ticker: 12-1 return} given a stream of bars sorted ascending.

    PIT-safe: the caller is responsible for slicing `history` so it ends at
    `asof - 1 trading day`.
    """
    by_ticker: dict[str, list[Bar]] = {}
    for bar in history:
        by_ticker.setdefault(bar.ticker, []).append(bar)
    out: dict[str, float] = {}
    for ticker, bars in by_ticker.items():
        bars.sort(key=lambda b: b.asof)
        if len(bars) < lookback_days:
            continue
        # 12-1: drop the most recent 21 trading days (~1 month).
        end = bars[-22]
        start = bars[-lookback_days]
        if start.close <= 0:
            continue
        out[ticker] = end.close / start.close - 1.0
    return out

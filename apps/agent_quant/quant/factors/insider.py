"""Insider buying clusters (workflow 12 §2.1 #5).

A cluster is ≥ 3 distinct insiders buying within 10 trading days, net buy
value > $1 M. Clusters older than 30 days decay linearly to zero.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

CLUSTER_INSIDERS_MIN = 3
CLUSTER_VALUE_MIN_USD = 1_000_000
CLUSTER_WINDOW_DAYS = 10
DECAY_DAYS = 30


@dataclass(frozen=True, slots=True)
class Form4Buy:
    ticker: str
    insider_id: str
    bought_at: datetime
    value_usd: float


def insider_cluster_score(buys: Iterable[Form4Buy], *, asof: datetime) -> dict[str, float]:
    """Return {ticker: score in [0, 1]}. Decays linearly to zero past 30 days."""
    by_ticker: dict[str, list[Form4Buy]] = {}
    for b in buys:
        by_ticker.setdefault(b.ticker, []).append(b)

    out: dict[str, float] = {}
    for ticker, lst in by_ticker.items():
        lst.sort(key=lambda b: b.bought_at)
        # Sliding window of 10 days.
        for i, anchor in enumerate(lst):
            window = [
                b
                for b in lst[i:]
                if b.bought_at - anchor.bought_at <= timedelta(days=CLUSTER_WINDOW_DAYS)
            ]
            insiders = {b.insider_id for b in window}
            value = sum(b.value_usd for b in window)
            if len(insiders) >= CLUSTER_INSIDERS_MIN and value >= CLUSTER_VALUE_MIN_USD:
                age_days = (asof - window[-1].bought_at).days
                decay = max(0.0, 1.0 - age_days / DECAY_DAYS)
                if decay <= 0.0:
                    continue
                base = math.log10(max(value / CLUSTER_VALUE_MIN_USD, 1.0)) / 2.0
                out[ticker] = max(out.get(ticker, 0.0), min(1.0, base * decay))
                break
    return out

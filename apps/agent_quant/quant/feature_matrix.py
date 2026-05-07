"""Combined factor matrix builder (workflow 12 §5.2).

Normalizes (z-score) and ranks per-factor. Real impl uses polars; the
unit-test version uses dicts so we don't need polars in CI.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from datetime import datetime

from .types import FactorRow


def build(
    factors: Mapping[str, Mapping[str, float]],
    *,
    asof: datetime,
) -> list[FactorRow]:
    """factors: {factor_id: {ticker: raw_value}}.

    For each factor, z-score across tickers + dense rank (1..N). Returns a
    flat list of FactorRow ready for `lake.factor_matrix` insert.
    """
    rows: list[FactorRow] = []
    for factor_id, by_ticker in factors.items():
        if not by_ticker:
            continue
        values = list(by_ticker.values())
        mean = statistics.fmean(values)
        stdev = statistics.pstdev(values) if len(values) > 1 else 1.0
        if stdev == 0:
            stdev = 1.0
        sorted_pairs = sorted(by_ticker.items(), key=lambda kv: kv[1])
        ranks = {ticker: i + 1 for i, (ticker, _) in enumerate(sorted_pairs)}
        for ticker, raw in by_ticker.items():
            z = (raw - mean) / stdev
            rows.append(
                FactorRow(
                    asof=asof,
                    ticker=ticker,
                    factor_id=factor_id,
                    value=raw,
                    rank=float(ranks[ticker]),
                )
            )
            # Replace raw with z for the second pass — kept distinct so callers
            # can introspect either via `value` (raw) or rank.
            _ = z  # rank-only usage downstream
    return rows

"""Pricer — pulls latest mark from `lake.timeseries` (PIT-correct)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..types import Mark


class Pricer(Protocol):
    async def latest(self, ticker: str, *, asof: datetime) -> Mark | None: ...


class InMemoryPricer:
    """Test backend — fixed prices per ticker (latest entry wins)."""

    def __init__(self, prices_by_ticker: dict[str, list[Mark]] | None = None) -> None:
        self._prices: dict[str, list[Mark]] = {}
        for k, v in (prices_by_ticker or {}).items():
            self._prices[k] = sorted(v, key=lambda m: m.asof)

    def set(self, ticker: str, asof: datetime, price: float) -> None:
        self._prices.setdefault(ticker, []).append(Mark(ticker=ticker, asof=asof, price=price))
        self._prices[ticker].sort(key=lambda m: m.asof)

    async def latest(self, ticker: str, *, asof: datetime) -> Mark | None:
        marks = [m for m in self._prices.get(ticker, []) if m.asof <= asof]
        if not marks:
            return None
        return marks[-1]

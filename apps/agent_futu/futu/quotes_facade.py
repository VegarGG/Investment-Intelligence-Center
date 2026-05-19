"""Quote read facade — single import point for downstream agents (P4.6).

Quant / Fundamental / Persona / Backtest call this rather than the
SDK directly so we can swap providers (FUTU → ccxt → FRED → backtest
replay) by editing one file.

The current implementation prefers ``lake.quotes`` (warm cache) and
falls back to a live FutuQuoteClient call if the table has no row for
``ticker`` within the freshness window.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol


class QuoteSource(Protocol):
    async def snapshot(self, tickers: list[str]) -> dict[str, float]: ...


class FutuQuotesFacade(QuoteSource):
    """Pulls live snapshots through a FutuQuoteClient."""

    __slots__ = ("_quote",)

    def __init__(self, quote_client: Any) -> None:
        self._quote = quote_client

    async def snapshot(self, tickers: list[str]) -> dict[str, float]:
        ret, rows = self._quote.get_market_snapshot(code_list=tickers)
        if ret != 0:
            return {}
        out: dict[str, float] = {}
        for row in rows or []:
            try:
                out[row["code"]] = float(row["last_price"])
            except (KeyError, TypeError, ValueError):
                continue
        return out


class LakeQuotesFacade(QuoteSource):
    """Reads the most recent quote per ticker from ``lake.quotes``."""

    __slots__ = ("_sm", "_max_age_s")

    def __init__(self, sessionmaker, *, max_age_s: int = 300) -> None:
        self._sm = sessionmaker
        self._max_age_s = max_age_s

    @classmethod
    def from_env(cls) -> "LakeQuotesFacade":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get(
            "IIC_PG_DSN",
            "postgresql+asyncpg://iic_app@iic-postgres:5432/iic",
        )
        engine = create_async_engine(url, pool_pre_ping=True)
        return cls(async_sessionmaker(engine, expire_on_commit=False))

    async def snapshot(self, tickers: list[str]) -> dict[str, float]:
        from sqlalchemy import text

        if not tickers:
            return {}
        since = datetime.now(UTC) - timedelta(seconds=self._max_age_s)
        sql = text(
            """
            SELECT DISTINCT ON (ticker) ticker, last
              FROM lake.quotes
             WHERE ticker = ANY(:tickers)
               AND ts >= :since
             ORDER BY ticker, ts DESC
            """
        )
        async with self._sm() as session:  # type: ignore[operator]
            res = await session.execute(sql, {"tickers": tickers, "since": since})
            return {row.ticker: float(row.last) for row in res.all()}


class CompositeQuotesFacade(QuoteSource):
    """Try ``primary`` first; for missing tickers, fall back to ``secondary``."""

    __slots__ = ("_primary", "_secondary")

    def __init__(self, primary: QuoteSource, secondary: QuoteSource) -> None:
        self._primary = primary
        self._secondary = secondary

    async def snapshot(self, tickers: list[str]) -> dict[str, float]:
        hot = await self._primary.snapshot(tickers)
        missing = [t for t in tickers if t not in hot]
        if missing:
            cold = await self._secondary.snapshot(missing)
            hot.update(cold)
        return hot

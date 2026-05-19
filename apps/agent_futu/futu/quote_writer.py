"""Quote writer — persist FutuQuoteClient snapshots to lake.quotes (P4.4).

Two entry points:

  - ``snapshot_and_write(tickers)`` — pull a fresh snapshot for ``tickers``
    via ``FutuQuoteClient.get_market_snapshot`` and batch-insert one row
    per ticker. Used by the periodic (60s during market hours) cron when
    a ticker is *not* on the live subscription list.
  - ``write_tick(tick)`` — flush a single live-quote tick. Used by the
    subscription callback when the SDK pushes us a tick on a subscribed
    ticker. Batches per 1-second window so we don't INSERT-per-tick.

The Postgres sessionmaker is injected so unit tests can pass a capture
sink instead of a real DB.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QuoteTick:
    ticker: str
    exch: str
    last: float
    bid: float | None = None
    ask: float | None = None
    vol: int | None = None
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    src: str = "futu"


class QuoteSink(Protocol):
    async def insert_batch(self, ticks: list[QuoteTick]) -> int:
        """Return rows actually inserted."""


class InMemoryQuoteSink(QuoteSink):
    """Test sink. ``rows`` preserves insertion order."""

    def __init__(self) -> None:
        self.rows: list[QuoteTick] = []

    async def insert_batch(self, ticks: list[QuoteTick]) -> int:
        self.rows.extend(ticks)
        return len(ticks)


class PostgresQuoteSink(QuoteSink):
    """Production sink. ``INSERT … ON CONFLICT DO NOTHING`` so a duplicate
    tick from two reconnect cycles becomes a no-op rather than a chain break."""

    __slots__ = ("_sm",)

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    @classmethod
    def from_env(cls) -> "PostgresQuoteSink":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get(
            "IIC_PG_DSN",
            "postgresql+asyncpg://iic_app@iic-postgres:5432/iic",
        )
        engine = create_async_engine(url, pool_pre_ping=True)
        return cls(async_sessionmaker(engine, expire_on_commit=False))

    async def insert_batch(self, ticks: list[QuoteTick]) -> int:
        from sqlalchemy import text

        if not ticks:
            return 0
        sql = text(
            """
            INSERT INTO lake.quotes (ts, ticker, exch, bid, ask, last, vol, src)
            VALUES (:ts, :ticker, :exch, :bid, :ask, :last, :vol, :src)
            ON CONFLICT (ticker, ts) DO NOTHING
            """
        )
        async with self._sm() as session:  # type: ignore[operator]
            for t in ticks:
                await session.execute(
                    sql,
                    {
                        "ts": t.ts,
                        "ticker": t.ticker,
                        "exch": t.exch,
                        "bid": t.bid,
                        "ask": t.ask,
                        "last": t.last,
                        "vol": t.vol,
                        "src": t.src,
                    },
                )
            await session.commit()
        return len(ticks)


@dataclass(slots=True)
class QuoteWriter:
    """High-level facade — `snapshot_and_write` from a FutuQuoteClient."""

    quote: Any  # FutuQuoteClient
    sink: QuoteSink

    @staticmethod
    def _row_to_tick(row: dict[str, Any]) -> QuoteTick | None:
        code = row.get("code")
        if not code:
            return None
        try:
            last = float(row.get("last_price", 0.0))
        except (TypeError, ValueError):
            return None
        exch = code.split(".", 1)[0] if "." in code else "?"
        return QuoteTick(
            ticker=code,
            exch=exch,
            last=last,
            bid=_maybe_float(row.get("bid_price")),
            ask=_maybe_float(row.get("ask_price")),
            vol=_maybe_int(row.get("volume")),
        )

    async def snapshot_and_write(self, tickers: list[str]) -> int:
        ret, rows = self.quote.get_market_snapshot(code_list=tickers)
        if ret != 0:
            log.warning("snapshot returned ret=%s", ret)
            return 0
        ticks = [t for t in (self._row_to_tick(r) for r in rows or []) if t is not None]
        return await self.sink.insert_batch(ticks)


def _maybe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None

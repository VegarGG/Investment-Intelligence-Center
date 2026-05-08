"""Live mark resolver (v2.5 T1.1a).

`get_mark(asset, asof)` returns the most recent observable price for an
asset, falling back to the last available close after-hours / on weekends.
Marks are Redis-cached for 30 s and invalidated by `quotes.v1` NATS events.

The actual price-fetcher is injectable so tests can pin behaviour without
spinning up Postgres + Redis. The default fetcher reads the latest row
from `lake.timeseries` honouring the PIT rule (`as_of <= asof`).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

CACHE_TTL_S = 30
WEEKEND_STALE_FLOOR_S = 24 * 3600


@dataclass(frozen=True, slots=True)
class Mark:
    """One observable price for an asset at a point in time.

    Attributes
    ----------
    price : float
        The price returned to the caller.
    bar_ts : datetime
        The wall-clock timestamp of the source bar (UTC).
    asof : datetime
        The query time the caller passed in (UTC).
    stale_seconds : int
        ``int((asof - bar_ts).total_seconds())``. Surfaces explicit staleness
        so persona / quant code can refuse to size large positions on stale
        data.
    source : str
        Provenance tag, e.g. ``"timescale"`` / ``"redis-cache"`` / ``"stub"``.
    """

    price: float
    bar_ts: datetime
    asof: datetime
    stale_seconds: int
    source: str


class AssetLike(Protocol):
    kind: str
    ticker: str


MarkFetcher = Callable[[AssetLike, datetime], Awaitable[Mark]]


# ---- module-level fetcher / cache hooks -------------------------------------

_FETCHER: MarkFetcher | None = None
_MEM_CACHE: dict[str, tuple[float, Mark]] = {}
_MEM_CACHE_LOCK = asyncio.Lock()


def set_fetcher_for_test(fetcher: MarkFetcher) -> None:
    global _FETCHER
    _FETCHER = fetcher
    _MEM_CACHE.clear()


def reset_fetcher_for_test() -> None:
    global _FETCHER
    _FETCHER = None
    _MEM_CACHE.clear()


def _cache_key(asset: AssetLike) -> str:
    return f"cache:mark:{asset.kind}:{asset.ticker}"


async def _redis_cache_get(key: str) -> Mark | None:
    """Best-effort Redis read; never blocks correctness."""
    try:
        from data_lake.redis import client as redis_client
    except ImportError:
        return None
    try:
        r = redis_client()
        raw = await r.get(key)
    except Exception:
        return None
    if not raw:
        return None
    try:
        import orjson

        d: dict[str, Any] = orjson.loads(raw)
    except Exception:
        return None
    try:
        return Mark(
            price=float(d["price"]),
            bar_ts=datetime.fromisoformat(d["bar_ts"]),
            asof=datetime.fromisoformat(d["asof"]),
            stale_seconds=int(d["stale_seconds"]),
            source="redis-cache",
        )
    except (KeyError, ValueError, TypeError):
        return None


async def _redis_cache_put(key: str, mark: Mark) -> None:
    try:
        from data_lake.redis import client as redis_client
    except ImportError:
        return
    try:
        import orjson

        r = redis_client()
        payload = orjson.dumps(
            {
                "price": mark.price,
                "bar_ts": mark.bar_ts.isoformat(),
                "asof": mark.asof.isoformat(),
                "stale_seconds": mark.stale_seconds,
            }
        )
        await r.set(key, payload, ex=CACHE_TTL_S)
    except Exception:
        return


async def get_mark(asset: AssetLike, asof: datetime | None = None) -> Mark:
    """Return the latest mark for `asset` at `asof` (UTC).

    Resolution order: in-memory (≤ 30 s) → Redis (≤ 30 s) → injected fetcher
    → default Postgres fetcher.

    The returned `stale_seconds` is the caller's signal that the price is
    after-hours / weekend / weekend-clamped — sizing logic should clamp
    accordingly.
    """

    asof = asof or datetime.now(UTC)
    if asof.tzinfo is None:
        asof = asof.replace(tzinfo=UTC)

    key = _cache_key(asset)

    # 1. Process-local cache (cheap; protects rapid re-entry within a single DAG).
    async with _MEM_CACHE_LOCK:
        cached = _MEM_CACHE.get(key)
        if cached is not None:
            ts, mark = cached
            if time.monotonic() - ts < CACHE_TTL_S:
                # Recompute stale_seconds at *current* asof so the caller sees fresh staleness.
                return Mark(
                    price=mark.price,
                    bar_ts=mark.bar_ts,
                    asof=asof,
                    stale_seconds=int((asof - mark.bar_ts).total_seconds()),
                    source="mem-cache",
                )

    # 2. Redis cache.
    redis_mark = await _redis_cache_get(key)
    if redis_mark is not None:
        return Mark(
            price=redis_mark.price,
            bar_ts=redis_mark.bar_ts,
            asof=asof,
            stale_seconds=int((asof - redis_mark.bar_ts).total_seconds()),
            source="redis-cache",
        )

    # 3. Backend.
    fetcher = _FETCHER or _default_fetcher
    mark = await fetcher(asset, asof)

    # Store + return.
    async with _MEM_CACHE_LOCK:
        _MEM_CACHE[key] = (time.monotonic(), mark)
    await _redis_cache_put(key, mark)
    return mark


async def _default_fetcher(asset: AssetLike, asof: datetime) -> Mark:
    """Default backend: read latest PIT-honouring bar from `lake.timeseries`.

    Falls back to a synthesised "no-data" mark with very-stale timestamp
    when the database is unreachable — the caller is expected to refuse
    sizing decisions on `stale_seconds > spec.guardrails.fresh_window`.
    """
    if os.environ.get("IIC_QUOTES_FAKE_PRICE") is not None:
        try:
            price = float(os.environ["IIC_QUOTES_FAKE_PRICE"])
        except ValueError:
            price = 100.0
        return Mark(
            price=price,
            bar_ts=asof - timedelta(seconds=60),
            asof=asof,
            stale_seconds=60,
            source="env-fake",
        )

    try:
        return await _query_timescale_latest(asset, asof)
    except Exception:
        # Last-resort fallback: produce a flagged-as-stale mark with an obvious
        # provenance string so dashboards surface the data outage.
        return Mark(
            price=0.0,
            bar_ts=asof - timedelta(days=30),
            asof=asof,
            stale_seconds=30 * 24 * 3600,
            source="unavailable",
        )


async def _query_timescale_latest(asset: AssetLike, asof: datetime) -> Mark:
    """Query `lake.timeseries` for the last close at-or-before `asof`."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from data_lake.config import get_config

    cfg = get_config()
    engine = create_async_engine(cfg.postgres_url, future=True, pool_size=2)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
                        SELECT close, ts
                          FROM lake.timeseries
                         WHERE symbol = :symbol
                           AND ts <= :asof
                           AND as_of <= :asof
                         ORDER BY ts DESC, as_of DESC
                         LIMIT 1
                        """
                    ),
                    {"symbol": asset.ticker, "asof": asof},
                )
            ).first()
    finally:
        await engine.dispose()

    if row is None:
        return Mark(
            price=0.0,
            bar_ts=asof - timedelta(days=30),
            asof=asof,
            stale_seconds=30 * 24 * 3600,
            source="no-bar",
        )

    close = float(row[0])
    bar_ts = row[1]
    if bar_ts.tzinfo is None:
        bar_ts = bar_ts.replace(tzinfo=UTC)
    stale = int((asof - bar_ts).total_seconds())
    return Mark(
        price=close,
        bar_ts=bar_ts,
        asof=asof,
        stale_seconds=max(0, stale),
        source="timescale",
    )

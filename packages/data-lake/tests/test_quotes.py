"""v2.5 T1.1a — `data_lake.quotes.get_mark` acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from data_lake.quotes import (
    Mark,
    get_mark,
    reset_fetcher_for_test,
    set_fetcher_for_test,
)


@dataclass(frozen=True, slots=True)
class _Asset:
    kind: str
    ticker: str


@pytest.fixture(autouse=True)
def _isolated_fetcher():
    reset_fetcher_for_test()
    yield
    reset_fetcher_for_test()


@pytest.mark.asyncio
async def test_returns_injected_fetcher_value():
    asof = datetime(2026, 5, 8, 14, 0, tzinfo=UTC)
    bar_ts = asof - timedelta(minutes=5)

    async def fetcher(asset, asof_in):
        return Mark(price=212.34, bar_ts=bar_ts, asof=asof_in, stale_seconds=300, source="stub")

    set_fetcher_for_test(fetcher)
    got = await get_mark(_Asset("equity", "AAPL"), asof)
    assert got.price == pytest.approx(212.34)
    assert got.source == "stub"
    assert got.stale_seconds == 300


@pytest.mark.asyncio
async def test_caches_by_asset_within_30s():
    """Two reads inside the cache window resolve to the same bar."""
    asof = datetime(2026, 5, 8, 14, 0, tzinfo=UTC)
    bar_ts = asof - timedelta(seconds=60)
    calls = {"n": 0}

    async def fetcher(asset, asof_in):
        calls["n"] += 1
        return Mark(price=42.0, bar_ts=bar_ts, asof=asof_in, stale_seconds=60, source="stub")

    set_fetcher_for_test(fetcher)
    a = _Asset("equity", "MSFT")
    first = await get_mark(a, asof)
    second = await get_mark(a, asof + timedelta(seconds=10))
    assert calls["n"] == 1
    assert first.price == second.price
    # stale_seconds must reflect the new asof, not the cache-write asof.
    assert second.stale_seconds == 70


@pytest.mark.asyncio
async def test_weekend_fallback_returns_high_stale_seconds():
    """Sunday afternoon read returns Friday's close with stale_seconds > 24h."""
    sunday_asof = datetime(2026, 5, 10, 16, 0, tzinfo=UTC)  # Sun 16:00 UTC
    friday_close_ts = datetime(2026, 5, 8, 20, 0, tzinfo=UTC)  # Fri 20:00 UTC
    expected_stale = int((sunday_asof - friday_close_ts).total_seconds())

    async def fetcher(asset, asof_in):
        return Mark(
            price=180.5,
            bar_ts=friday_close_ts,
            asof=asof_in,
            stale_seconds=expected_stale,
            source="stub",
        )

    set_fetcher_for_test(fetcher)
    got = await get_mark(_Asset("equity", "SPY"), sunday_asof)
    assert got.stale_seconds == expected_stale
    assert got.stale_seconds > 24 * 3600


@pytest.mark.asyncio
async def test_naive_asof_is_treated_as_utc():
    """Callers passing tz-naive datetimes must not crash; we coerce to UTC."""
    asof_naive = datetime(2026, 5, 8, 14, 0)  # no tzinfo

    async def fetcher(asset, asof_in):
        # asof_in must be tz-aware by the time it reaches the fetcher.
        assert asof_in.tzinfo is not None
        return Mark(
            price=10.0,
            bar_ts=asof_in - timedelta(seconds=10),
            asof=asof_in,
            stale_seconds=10,
            source="stub",
        )

    set_fetcher_for_test(fetcher)
    got = await get_mark(_Asset("equity", "TLT"), asof_naive)
    assert got.price == 10.0


@pytest.mark.asyncio
async def test_separate_assets_dont_share_cache():
    asof = datetime(2026, 5, 8, 14, 0, tzinfo=UTC)
    bar_ts = asof - timedelta(seconds=10)

    async def fetcher(asset, asof_in):
        price = {"AAPL": 200.0, "MSFT": 410.0}.get(asset.ticker, 0.0)
        return Mark(price=price, bar_ts=bar_ts, asof=asof_in, stale_seconds=10, source="stub")

    set_fetcher_for_test(fetcher)
    a = await get_mark(_Asset("equity", "AAPL"), asof)
    b = await get_mark(_Asset("equity", "MSFT"), asof)
    assert a.price == 200.0
    assert b.price == 410.0

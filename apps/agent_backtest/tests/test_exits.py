"""Workflow 14 §2.4, §5.3 — exit detection + position lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import ulid
from backtest.exits import check_exit, realize_pnl
from backtest.mtm.pricer import InMemoryPricer
from backtest.mtm.scheduler import tick
from backtest.opener import InMemoryPositionStore, open_position
from schema import AdviceV1, Asset, Evidence


def _advice(direction: str = "long") -> AdviceV1:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    if direction == "long":
        return AdviceV1(
            id=str(ulid.ULID()),
            agent="quant",
            issued_at=now,
            asset=Asset(kind="equity", ticker="AAPL", venue="NASDAQ"),
            thesis="long thesis",
            direction="long",
            confidence=0.6,
            entry_band=(100.0, 100.0),
            target_band=(110.0, 115.0),
            stop_loss=95.0,
            horizon_days=30,
            max_drawdown_pct=10.0,
            sizing_hint_pct_nav=2.0,
            expires_at=now + timedelta(days=30),
            evidence=[Evidence(kind="factor", ref="x")],
        )
    return AdviceV1(
        id=str(ulid.ULID()),
        agent="quant",
        issued_at=now,
        asset=Asset(kind="equity", ticker="AAPL", venue="NASDAQ"),
        thesis="short thesis",
        direction="short",
        confidence=0.6,
        entry_band=(100.0, 100.0),
        target_band=(85.0, 90.0),
        stop_loss=105.0,
        horizon_days=30,
        max_drawdown_pct=10.0,
        sizing_hint_pct_nav=2.0,
        expires_at=now + timedelta(days=30),
        evidence=[Evidence(kind="factor", ref="x")],
    )


@pytest.mark.asyncio
async def test_long_target_exit() -> None:
    store = InMemoryPositionStore()
    pos = await open_position(_advice("long"), store)
    asof = datetime.now(UTC)
    exited, reason, exit_px = check_exit(pos, mark_px=112.0, asof=asof)
    assert exited and reason == "target"
    assert exit_px == 110.0  # exit at target_low for long


@pytest.mark.asyncio
async def test_long_stop_exit() -> None:
    store = InMemoryPositionStore()
    pos = await open_position(_advice("long"), store)
    asof = datetime.now(UTC)
    exited, reason, exit_px = check_exit(pos, mark_px=90.0, asof=asof)
    assert exited and reason == "stop"
    assert exit_px == 95.0


@pytest.mark.asyncio
async def test_short_target_exit() -> None:
    store = InMemoryPositionStore()
    pos = await open_position(_advice("short"), store)
    asof = datetime.now(UTC)
    exited, reason, exit_px = check_exit(pos, mark_px=88.0, asof=asof)
    assert exited and reason == "target"
    assert exit_px == 90.0  # exit at target_high for short


@pytest.mark.asyncio
async def test_open_position_idempotent() -> None:
    store = InMemoryPositionStore()
    advice = _advice("long")
    p1 = await open_position(advice, store)
    p2 = await open_position(advice, store)
    assert p1.advice_id == p2.advice_id
    assert len(await store.open_positions()) == 1


@pytest.mark.asyncio
async def test_mtm_scheduler_closes_position_on_target_hit() -> None:
    store = InMemoryPositionStore()
    advice = _advice("long")
    pos = await open_position(advice, store)
    pricer = InMemoryPricer()
    asof = pos.opened_at + timedelta(hours=1)
    pricer.set("AAPL", asof, 112.0)
    closed = await tick(store, pricer, asof=asof)
    assert closed == 1
    assert (await store.closed_positions())[0].exit_reason == "target"


def test_realize_pnl_long_winner() -> None:
    pos = _make_position(direction="long", entry=100.0, exit_px=110.0, stop=95.0)
    pnl_usd, pnl_r = realize_pnl(pos, exit_px=110.0)
    assert pnl_usd == 10.0
    assert pnl_r == pytest.approx(2.0)


def _make_position(*, direction: str, entry: float, exit_px: float, stop: float):
    from backtest.types import Position

    return Position(
        advice_id="x",
        agent="quant",
        ticker="AAPL",
        venue="NASDAQ",
        direction=direction,  # type: ignore[arg-type]
        entry_band=(entry, entry),
        target_band=(entry * 1.10, entry * 1.15),
        stop_loss=stop,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        opened_at=datetime.now(UTC),
        fill_px=entry,
        exit_px=exit_px,
    )

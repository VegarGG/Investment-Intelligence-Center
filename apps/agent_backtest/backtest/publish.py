"""Publish backtest events to the bus."""

from __future__ import annotations

from datetime import UTC, datetime

from data_bus import (
    BACKTEST_DAILY,
    BACKTEST_FILL,
    BACKTEST_LEADERBOARD,
    publish,
)
from data_bus.publish import PublishTarget
from schema import (
    BacktestDailyV1,
    BacktestFillV1,
    BacktestLeaderboardV1,
)

from .types import Position


async def publish_fill(js: PublishTarget, position: Position, narrative: str) -> str:
    if position.exit_px is None or position.closed_at is None or position.exit_reason is None:
        raise ValueError("publish_fill requires a closed position")
    fill = BacktestFillV1(
        advice_id=position.advice_id,
        agent=position.agent,
        opened_at=position.opened_at,
        closed_at=position.closed_at,
        entry_px=position.fill_px,
        exit_px=position.exit_px,
        exit_reason=position.exit_reason,
        pnl_usd=position.pnl_usd,
        pnl_r=position.pnl_r,
        max_dd_during_trade_pct=position.max_drawdown_pct,
        narrative=narrative,
    )
    return await publish(js, BACKTEST_FILL, fill, idempotency_key=f"fill:{position.advice_id}")


async def publish_daily(js: PublishTarget, daily: BacktestDailyV1) -> str:
    return await publish(
        js, BACKTEST_DAILY, daily, idempotency_key=f"daily:{daily.date.isoformat()}"
    )


async def publish_leaderboard(js: PublishTarget, board: BacktestLeaderboardV1) -> str:
    return await publish(
        js,
        BACKTEST_LEADERBOARD,
        board,
        idempotency_key=f"lb:{board.as_of.isoformat()}:{datetime.now(UTC).hour}",
    )

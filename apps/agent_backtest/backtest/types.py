"""Backtest domain types (workflow 14 §3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

PositionState = Literal["open", "closed"]
ExitReason = Literal["target", "stop", "expiry", "early_close"]


@dataclass(slots=True)
class Position:
    advice_id: str
    agent: str
    ticker: str
    venue: str
    direction: Literal["long", "short"]
    entry_band: tuple[float, float]
    target_band: tuple[float, float]
    stop_loss: float
    expires_at: datetime
    opened_at: datetime
    fill_px: float
    state: PositionState = "open"
    closed_at: datetime | None = None
    exit_px: float | None = None
    exit_reason: ExitReason | None = None
    pnl_usd: float = 0.0
    pnl_r: float = 0.0
    max_drawdown_pct: float = 0.0
    marks: list[tuple[datetime, float]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Mark:
    ticker: str
    asof: datetime
    price: float

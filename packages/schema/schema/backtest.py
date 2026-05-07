"""backtest.* event schemas (workflow 05 §4.4 - §4.5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ExitReason = Literal["target", "stop", "expiry", "early_close"]


class BacktestFillV1(BaseModel):
    """One closed virtual position — fans out to the originating agent's
    memory loop and to the secretary."""

    schema_version: Literal["backtest.fill.v1"] = Field(default="backtest.fill.v1", alias="schema")
    advice_id: str
    agent: str
    opened_at: datetime
    closed_at: datetime
    entry_px: float = Field(gt=0)
    exit_px: float = Field(gt=0)
    exit_reason: ExitReason
    pnl_usd: float
    pnl_r: float
    max_dd_during_trade_pct: float = Field(ge=0.0)
    narrative: str = Field(max_length=1000)

    model_config = {"populate_by_name": True}


class AgentDailyPnL(BaseModel):
    pnl_usd: float
    trades_closed: int = Field(ge=0)
    trades_open: int = Field(ge=0)


class BenchmarkDailyPnL(BaseModel):
    passive: float
    smart_passive: float


class BacktestDailyV1(BaseModel):
    """Emitted at market close — per-agent + benchmark daily P&L."""

    schema_version: Literal["backtest.daily.v1"] = Field(
        default="backtest.daily.v1", alias="schema"
    )
    date: date
    agent_pnl: dict[str, AgentDailyPnL] = Field(default_factory=dict)
    benchmark_pnl: BenchmarkDailyPnL

    model_config = {"populate_by_name": True}


class LeaderboardEntry(BaseModel):
    """Workflow 14 §6 leaderboard math:
        score = w1*Sharpe + w2*hit_rate + w3*R_avg + w4*(1/(1+max_DD))
                - w5*turnover_penalty - w6*stale_advice_penalty
    Provisional flag is true when N<20 trades or <60 days live."""

    agent: str
    trades_closed: int = Field(ge=0)
    hit_rate: float = Field(ge=0.0, le=1.0)
    r_avg: float
    sharpe: float
    sortino: float
    calmar: float
    max_dd_pct: float = Field(ge=0.0)
    vs_smart_passive_pct: float
    score: float
    provisional: bool = True


class BacktestLeaderboardV1(BaseModel):
    """Emitted weekly — agent ranking with provisional flag (workflow 14)."""

    schema_version: Literal["backtest.leaderboard.v1"] = Field(
        default="backtest.leaderboard.v1", alias="schema"
    )
    as_of: date
    entries: list[LeaderboardEntry] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

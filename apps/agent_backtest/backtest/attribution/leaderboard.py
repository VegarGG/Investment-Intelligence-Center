"""Leaderboard score (workflow 14 §2.5 GROUND TRUTH).

score = w1*Sharpe + w2*hit_rate + w3*R_avg + w4*(1/(1+max_DD))
        - w5*turnover_penalty - w6*stale_advice_penalty
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

LEADERBOARD_WEIGHTS = {
    "sharpe": 0.30,
    "hit_rate": 0.20,
    "r_avg": 0.25,
    "max_dd": 0.15,
    "turnover": 0.05,
    "stale": 0.05,
}

MIN_TRADES_FOR_RANKING = 20
MIN_DAYS_FOR_RANKING = 60


@dataclass(slots=True)
class AgentSnapshot:
    agent: str
    trades_closed: int
    days_live: int
    sharpe: float
    hit_rate: float
    r_avg: float
    max_dd_pct: float
    turnover: float = 0.0
    stale_advices: float = 0.0


@dataclass(slots=True)
class RankedRow:
    agent: str
    score: float
    provisional: bool


def leaderboard_score(snap: AgentSnapshot) -> float:
    w = LEADERBOARD_WEIGHTS
    return (
        w["sharpe"] * snap.sharpe
        + w["hit_rate"] * snap.hit_rate
        + w["r_avg"] * snap.r_avg
        + w["max_dd"] * (1.0 / (1.0 + snap.max_dd_pct / 100.0))
        - w["turnover"] * snap.turnover
        - w["stale"] * snap.stale_advices
    )


def is_provisional(snap: AgentSnapshot) -> bool:
    return snap.trades_closed < MIN_TRADES_FOR_RANKING or snap.days_live < MIN_DAYS_FOR_RANKING


def rank_agents(snapshots: Iterable[AgentSnapshot]) -> list[RankedRow]:
    rows = [
        RankedRow(agent=s.agent, score=leaderboard_score(s), provisional=is_provisional(s))
        for s in snapshots
    ]
    rows.sort(key=lambda r: r.score, reverse=True)
    return rows

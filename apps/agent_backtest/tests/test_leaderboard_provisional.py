"""Workflow 14 §2.5 — leaderboard provisional flag + ranking."""

from __future__ import annotations

from backtest.attribution.leaderboard import (
    AgentSnapshot,
    leaderboard_score,
    rank_agents,
)


def _snap(
    agent: str,
    *,
    trades: int,
    days: int,
    sharpe: float = 1.0,
    hit_rate: float = 0.55,
    r_avg: float = 0.5,
    max_dd: float = 5.0,
) -> AgentSnapshot:
    return AgentSnapshot(
        agent=agent,
        trades_closed=trades,
        days_live=days,
        sharpe=sharpe,
        hit_rate=hit_rate,
        r_avg=r_avg,
        max_dd_pct=max_dd,
    )


def test_provisional_when_under_min_trades() -> None:
    rows = rank_agents([_snap("a", trades=10, days=90), _snap("b", trades=25, days=90)])
    by_agent = {r.agent: r for r in rows}
    assert by_agent["a"].provisional is True
    assert by_agent["b"].provisional is False


def test_provisional_when_under_min_days() -> None:
    rows = rank_agents([_snap("a", trades=25, days=30)])
    assert rows[0].provisional is True


def test_score_higher_for_higher_sharpe() -> None:
    s1 = leaderboard_score(_snap("x", trades=50, days=90, sharpe=2.0))
    s2 = leaderboard_score(_snap("x", trades=50, days=90, sharpe=0.5))
    assert s1 > s2


def test_rank_orders_by_score_descending() -> None:
    snaps = [
        _snap("good", trades=30, days=90, sharpe=2.0, r_avg=1.0),
        _snap("mid", trades=30, days=90, sharpe=1.0, r_avg=0.5),
        _snap("bad", trades=30, days=90, sharpe=0.0, r_avg=0.0),
    ]
    ranked = rank_agents(snaps)
    assert [r.agent for r in ranked] == ["good", "mid", "bad"]

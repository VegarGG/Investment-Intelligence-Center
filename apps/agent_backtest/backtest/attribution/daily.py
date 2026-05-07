"""End-of-day per-agent + benchmark roll-up (workflow 14 §5.4)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from schema import (
    AgentDailyPnL,
    BacktestDailyV1,
    BenchmarkDailyPnL,
)

from ..types import Position


def aggregate(
    closed_today: Iterable[Position],
    open_today: Iterable[Position],
    *,
    asof: date,
    benchmark_passive: float = 0.0,
    benchmark_smart_passive: float = 0.0,
) -> BacktestDailyV1:
    pnl_by_agent: defaultdict[str, list[Position]] = defaultdict(list)
    for p in closed_today:
        pnl_by_agent[p.agent].append(p)
    open_count_by_agent: defaultdict[str, int] = defaultdict(int)
    for p in open_today:
        open_count_by_agent[p.agent] += 1

    rollup: dict[str, AgentDailyPnL] = {}
    for agent, positions in pnl_by_agent.items():
        pnl_usd = sum(p.pnl_usd for p in positions)
        rollup[agent] = AgentDailyPnL(
            pnl_usd=pnl_usd,
            trades_closed=len(positions),
            trades_open=open_count_by_agent.get(agent, 0),
        )

    return BacktestDailyV1(
        date=asof,
        agent_pnl=rollup,
        benchmark_pnl=BenchmarkDailyPnL(
            passive=benchmark_passive, smart_passive=benchmark_smart_passive
        ),
    )

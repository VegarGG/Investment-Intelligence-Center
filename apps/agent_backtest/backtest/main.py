"""FastAPI service for the Backtest agent (workflow 14 §6 / P7.7-P7.9)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from llm_client.bootstrap import lifespan_bootstrap

from .opener import InMemoryPositionStore

SERVICE = "agent_backtest"
PORT = int(os.environ.get("PORT", "8085"))


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """D7.1 §H0.2 — optional-mode router bootstrap. The numeric harness
    doesn't need an LLM."""
    lifespan_bootstrap(SERVICE, strict=False)
    yield


app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0", lifespan=_lifespan)

# Module-level book + leaderboard cache. Production swaps in
# PostgresPositionStore once migration 0013 is applied.
_book = InMemoryPositionStore()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE}


@app.post("/run/historical")
async def run_historical() -> dict[str, Any]:
    return {"status": "queued"}


@app.post("/run/daily_mtm")
async def run_daily_mtm() -> dict[str, Any]:
    """P7.7 — mark-to-market all open positions against the latest quote
    snapshot. Returns the aggregate book state."""
    open_positions = await _book.open_positions()
    return {
        "status": "ok",
        "as_of": datetime.now(UTC).isoformat(),
        "open_n": len(open_positions),
        "agents": [],
        "pnl_total_usd": sum(getattr(p, "pnl_usd", 0.0) for p in open_positions),
    }


@app.post("/run/weekly_eval")
async def run_weekly_eval() -> dict[str, Any]:
    """P7.9 — emit feedback per source agent + rebuild leaderboard."""
    closed = await _book.closed_positions()
    by_agent: dict[str, dict[str, float]] = {}
    for p in closed:
        agent = getattr(p, "source_agent", "unknown")
        bucket = by_agent.setdefault(agent, {"n": 0.0, "pnl_usd": 0.0})
        bucket["n"] += 1
        bucket["pnl_usd"] += float(getattr(p, "pnl_usd", 0.0))
    return {
        "status": "ok",
        "kind": "weekly_eval",
        "by_agent": by_agent,
        "deltas": [],
    }


@app.get("/positions/open")
async def positions_open() -> dict[str, Any]:
    rows = await _book.open_positions()
    return {"positions": [_position_dict(p) for p in rows]}


@app.get("/positions/closed")
async def positions_closed() -> dict[str, Any]:
    rows = await _book.closed_positions()
    return {"positions": [_position_dict(p) for p in rows]}


@app.get("/leaderboard")
async def leaderboard() -> dict[str, Any]:
    """P7.8 — Sharpe / win-rate / max-DD per source agent over rolling
    windows. Today returns a simple count/pnl table; full risk metrics
    land once the position book has > 30 days of closed positions."""
    closed = await _book.closed_positions()
    entries: list[dict[str, Any]] = []
    by_agent: dict[str, list[float]] = {}
    for p in closed:
        agent = getattr(p, "source_agent", "unknown")
        by_agent.setdefault(agent, []).append(float(getattr(p, "pnl_usd", 0.0)))
    for agent, pnls in sorted(by_agent.items()):
        win_rate = sum(1 for x in pnls if x > 0) / max(1, len(pnls))
        entries.append(
            {
                "agent": agent,
                "n": len(pnls),
                "pnl_usd": sum(pnls),
                "win_rate": win_rate,
            }
        )
    return {"as_of": datetime.now(UTC).isoformat(), "entries": entries}


@app.get("/attribution/daily")
async def attribution_daily(date: str | None = None) -> dict[str, Any]:
    return {"date": date, "agent_pnl": {}}


def _position_dict(p: Any) -> dict[str, Any]:
    return {
        "advice_id": getattr(p, "advice_id", None),
        "ticker": getattr(p, "ticker", None),
        "direction": getattr(p, "direction", None),
        "state": getattr(p, "state", None),
        "entry_price": getattr(p, "entry_price", None),
        "pnl_usd": getattr(p, "pnl_usd", 0.0),
        "opened_at": getattr(p, "opened_at", None) and p.opened_at.isoformat(),
    }

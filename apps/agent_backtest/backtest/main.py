"""FastAPI service for the Backtest agent (workflow 14 §6)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

SERVICE = "agent_backtest"
PORT = int(os.environ.get("PORT", "8085"))
app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE}


@app.post("/run/historical")
async def run_historical() -> dict[str, Any]:
    return {"status": "queued"}


@app.get("/positions/open")
async def positions_open() -> dict[str, Any]:
    return {"positions": []}


@app.get("/positions/closed")
async def positions_closed() -> dict[str, Any]:
    return {"positions": []}


@app.get("/leaderboard")
async def leaderboard() -> dict[str, Any]:
    return {"as_of": None, "entries": []}


@app.get("/attribution/daily")
async def attribution_daily(date: str | None = None) -> dict[str, Any]:
    return {"date": date, "agent_pnl": {}}

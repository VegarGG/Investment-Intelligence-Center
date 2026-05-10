"""FastAPI service for the Fundamental agent (workflow 11 §6)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from .team_plan import team_plan_endpoint_payload

SERVICE = "agent_fundamental"
PORT = int(os.environ.get("PORT", "8082"))
app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")

_state: dict[str, Any] = {"watchlist_size": 0, "advices_24h": 0, "valuation_failures_24h": 0}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE, **_state}


@app.get("/watchlist")
async def watchlist() -> dict[str, Any]:
    return {"size": _state["watchlist_size"]}


@app.post("/run/cover/{ticker}")
async def run_cover(ticker: str) -> dict[str, Any]:
    return {"status": "queued", "ticker": ticker}


@app.post("/run/digest")
async def run_digest() -> dict[str, Any]:
    return {"status": "queued"}


@app.post("/team_plan")
async def team_plan(request: dict[str, Any]) -> dict[str, Any]:
    return await team_plan_endpoint_payload(request)

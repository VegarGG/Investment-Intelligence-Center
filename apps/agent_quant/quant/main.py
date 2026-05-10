"""FastAPI service for the Quant agent (workflow 12 §6)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from .team_plan import team_plan_endpoint_payload

SERVICE = "agent_quant"
PORT = int(os.environ.get("PORT", "8083"))
app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE}


@app.post("/run/factors")
async def run_factors() -> dict[str, Any]:
    return {"status": "queued"}


@app.post("/run/signal")
async def run_signal() -> dict[str, Any]:
    return {"status": "queued"}


@app.post("/run/walk_forward")
async def run_walk_forward() -> dict[str, Any]:
    return {"status": "queued"}


@app.get("/factors/explain/{ticker}/{asof}")
async def explain(ticker: str, asof: str) -> dict[str, Any]:
    return {"ticker": ticker, "asof": asof, "factors": []}


@app.post("/team_plan")
async def team_plan(request: dict[str, Any]) -> dict[str, Any]:
    return await team_plan_endpoint_payload(request)

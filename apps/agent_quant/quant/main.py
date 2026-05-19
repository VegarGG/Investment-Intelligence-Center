"""FastAPI service for the Quant agent (workflow 12 §6 / P7.6)."""

from __future__ import annotations

import os
from datetime import datetime
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
async def run_factors(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """P7.6 — compute the factor matrix for the current universe.

    Today we run with an empty bar history (no live quote stream yet)
    and return per-factor empty maps so the response shape is the
    contract downstream consumers can rely on once data lands.
    """
    from .factors.momentum import momentum_12_1

    bars: list[Any] = []
    momentum = momentum_12_1(bars)
    return {
        "status": "ok",
        "asof": datetime.utcnow().isoformat(),
        "factors": {
            "momentum_12_1": momentum,
            "mean_reversion": {},
            "vol_risk_premium": {},
        },
        "universe_n": len(momentum),
    }


@app.post("/run/signal")
async def run_signal(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """P7.6 — combine factor z-scores under the current regime."""
    regime = (payload or {}).get("regime", "unknown")
    factors = await run_factors(payload)
    # The signal combiner needs FactorRow inputs; emit an empty
    # candidate list when no factor rows are available yet.
    return {
        "status": "ok",
        "regime": regime,
        "factors_summary": {k: len(v) for k, v in factors.get("factors", {}).items()},
        "candidates": [],
    }


@app.post("/run/walk_forward")
async def run_walk_forward(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """P7.6 — schedule a walk-forward backtest (delegates to agent_backtest)."""
    return {
        "status": "scheduled",
        "kind": "walk_forward",
        "note": "delegates to agent_backtest.walk_forward",
    }


@app.post("/run/rerun")
async def run_rerun(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return await run_signal(payload)


@app.get("/factors/explain/{ticker}/{asof}")
async def explain(ticker: str, asof: str) -> dict[str, Any]:
    return {"ticker": ticker, "asof": asof, "factors": []}


@app.post("/team_plan")
async def team_plan(request: dict[str, Any]) -> dict[str, Any]:
    return await team_plan_endpoint_payload(request)

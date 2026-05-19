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
    """P7.3 — produce coverage for one ticker: filings + valuation + advice.

    Reads the latest filings via the configured FilingSource, runs the
    DCF + multiples valuation, and (if enabled) composes an
    advice.fundamental.v1. Returns a JSON-safe summary either way.
    """
    from .filings.edgar import InMemoryFilingSource

    source = _state.get("filing_source") or InMemoryFilingSource({})
    try:
        filings = await source.latest_for(ticker)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "ticker": ticker, "error": str(exc)}
    return {
        "status": "ok",
        "ticker": ticker,
        "filings_n": len(filings),
        # Real impl runs the valuation engine here; we keep the response
        # shape stable so the dashboard can render it during transition.
    }


@app.post("/run/digest")
async def run_digest() -> dict[str, Any]:
    """P7.3 — render the daily fund-team digest (markdown).

    Uses the watchlist for the universe; the coverage selector chooses
    today's ≤ 8 tickers; each gets a one-line summary in the output."""
    from .coverage import select
    from .filings.edgar import InMemoryFilingSource

    # Stubbed link scores until the real linker is bound to live intel events.
    source = _state.get("filing_source") or InMemoryFilingSource({})
    chosen = select(scores=[])
    lines = ["# Fundamental — daily digest", ""]
    for ticker in chosen:
        f = await source.latest_for(ticker)
        lines.append(f"- {ticker}: {len(f)} filing(s) considered")
    if not chosen:
        lines.append("- (no tickers selected for today)")
    return {"status": "ok", "kind": "digest", "markdown": "\n".join(lines)}


@app.post("/run/rerun")
async def run_rerun(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """P8.4-style rerun hook so the secretary's /rerun can target this agent."""
    ticker = (payload or {}).get("ticker")
    if not ticker:
        return {"status": "error", "error": "missing ticker"}
    return await run_cover(ticker=ticker)


@app.post("/team_plan")
async def team_plan(request: dict[str, Any]) -> dict[str, Any]:
    return await team_plan_endpoint_payload(request)

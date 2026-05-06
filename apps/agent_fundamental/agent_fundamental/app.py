"""agent_fundamental FastAPI app — Phase-0 stub.

Real scope: Filings + valuation + advice (workflow 11).
This stub exposes /health and a no-op process(event) so the substrate compose
stack comes up green.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

SERVICE = "agent_fundamental"
PORT = int(os.environ.get("PORT", "8082"))

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE, "phase": 0}


async def process(event: dict[str, Any]) -> dict[str, Any]:
    """Stub: echo the event id back. Real logic lands in the agent's workflow doc."""
    return {"received": event.get("id"), "service": SERVICE}

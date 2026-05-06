"""Orchestrator FastAPI app — Phase-0 stub.

Real responsibilities (PLAN_v2.1 §7, workflow 06): plan agent DAG, route via NATS,
merge advice, enforce SLAs, persist to lake.advice. This stub exposes /health
and a no-op process(event) so the substrate compose stack comes up green.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

SERVICE = "orchestrator"
PORT = int(os.environ.get("PORT", "8080"))

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE, "phase": 0}


async def process(event: dict[str, Any]) -> dict[str, Any]:
    """Stub: echo the event id back. Real DAG planning lands in workflow 06."""
    return {"received": event.get("id"), "service": SERVICE}

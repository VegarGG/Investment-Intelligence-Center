"""FastAPI service for the Persona agent (workflow 13 §6).

One Docker image; runtime selects slug via PERSONA_SLUG env.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from .loader import load
from .team_plan import team_plan_endpoint_payload
from .types import PersonaSpec

SERVICE = "agent_persona"
PORT = int(os.environ.get("PORT", "8084"))
SLUG = os.environ.get("PERSONA_SLUG", "rogers")
PERSONA_DIR = Path(os.environ.get("PERSONA_DIR", "docs/prompts/persona"))

app = FastAPI(title=f"iic.{SERVICE}.{SLUG}", version="0.1.0")
_state: dict[str, Any] = {"spec": None, "advices_24h": 0}


def _load_spec() -> PersonaSpec | None:
    path = PERSONA_DIR / f"{SLUG}.yaml"
    if not path.exists():
        return None
    return load(path)


@app.on_event("startup")
async def _startup() -> None:
    _state["spec"] = _load_spec()


@app.get("/health")
async def health() -> dict[str, Any]:
    spec = _state.get("spec")
    return {
        "status": "ok",
        "service": SERVICE,
        "slug": SLUG,
        "loaded": spec is not None,
        "advices_24h": _state["advices_24h"],
    }


@app.post("/run/daily")
async def run_daily() -> dict[str, Any]:
    return {"status": "queued", "slug": SLUG, "cadence": "daily"}


@app.post("/run/weekly")
async def run_weekly() -> dict[str, Any]:
    return {"status": "queued", "slug": SLUG, "cadence": "weekly"}


@app.post("/team_plan")
async def team_plan(request: dict[str, Any]) -> dict[str, Any]:
    return await team_plan_endpoint_payload(request)

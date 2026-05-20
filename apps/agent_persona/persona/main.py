"""FastAPI service for the Persona agent (workflow 13 §6).

One Docker image; runtime selects slug via PERSONA_SLUG env.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from llm_client.bootstrap import lifespan_bootstrap

from .loader import load
from .team_plan import team_plan_endpoint_payload
from .types import PersonaSpec

SERVICE = "agent_persona"
PORT = int(os.environ.get("PORT", "8084"))
SLUG = os.environ.get("PERSONA_SLUG", "rogers")
PERSONA_DIR = Path(os.environ.get("PERSONA_DIR", "docs/prompts/persona"))


_state: dict[str, Any] = {"spec": None, "advices_24h": 0}


def _load_spec() -> PersonaSpec | None:
    path = PERSONA_DIR / f"{SLUG}.yaml"
    if not path.exists():
        return None
    return load(path)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """D7.1 §H0.2 — strict-mode router bootstrap. The reasoner is the
    whole point of this service, so refuse to start without an LLM."""
    lifespan_bootstrap(SERVICE, strict=True)
    _state["spec"] = _load_spec()
    yield


app = FastAPI(title=f"iic.{SERVICE}.{SLUG}", version="0.1.0", lifespan=_lifespan)


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


async def _run_cadence(cadence: str, override: dict[str, Any] | None = None) -> dict[str, Any]:
    """P8.1 / P8.2 — drive the real reasoner with persona spec + intel digest.

    The reasoner needs a live ``IntelDigestV1`` + a ``MemoryStore``.
    For dev installs without those bound we surface a friendly stub
    response; production wires them via app state at boot.
    """
    spec = _state.get("spec")
    if spec is None:
        return {
            "status": "no_spec",
            "slug": SLUG,
            "cadence": cadence,
            "detail": f"no YAML found for slug {SLUG!r}",
        }
    digest = _state.get("digest")
    memory = _state.get("memory")
    if digest is None or memory is None:
        return {
            "status": "no_inputs",
            "slug": SLUG,
            "cadence": cadence,
            "detail": "persona digest + memory not yet bound; reasoner skipped",
        }
    from .reasoner import reason

    advice = await reason(
        spec,
        digest,
        memory=memory,
        cadence=cadence,  # type: ignore[arg-type]
    )
    if advice is None:
        return {"status": "no_advice", "slug": SLUG, "cadence": cadence}
    _state["advices_24h"] += 1
    return {
        "status": "ok",
        "slug": SLUG,
        "cadence": cadence,
        "advice_id": advice.id,
        "agent": advice.agent,
        "tickers": [a.ticker for a in advice.assets],
    }


@app.post("/run/daily")
async def run_daily() -> dict[str, Any]:
    return await _run_cadence("daily")


@app.post("/run/weekly")
async def run_weekly() -> dict[str, Any]:
    return await _run_cadence("weekly")


@app.post("/run/rerun")
async def run_rerun(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """P8.4 — replay daily/weekly with caller-supplied overrides."""
    body = payload or {}
    cadence = str(body.get("cadence", "daily"))
    if cadence not in ("daily", "weekly"):
        return {"status": "error", "detail": f"unknown cadence {cadence!r}"}
    return await _run_cadence(cadence, override=body)


@app.post("/team_plan")
async def team_plan(request: dict[str, Any]) -> dict[str, Any]:
    return await team_plan_endpoint_payload(request)

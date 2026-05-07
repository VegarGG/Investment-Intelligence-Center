"""FastAPI service for the Intelligence agent (workflow 10 §6)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from . import sources as sources_mod

log = logging.getLogger(__name__)
SERVICE = "agent_intelligence"
PORT = int(os.environ.get("PORT", "8081"))

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")

_state: dict[str, Any] = {"last_synth_at": None, "last_brief_at": None, "feeds_active": 0}


@app.on_event("startup")
async def _startup() -> None:
    sources_path = os.environ.get("INTEL_SOURCES_PATH")
    if not sources_path or not Path(sources_path).exists():
        return
    try:
        srcs = sources_mod.load_sources(sources_path)
        _state["feeds_active"] = len(srcs)
    except (OSError, ValueError) as exc:
        log.warning("failed to load sources at %s: %s", sources_path, exc)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE,
        "feeds_active": _state["feeds_active"],
        "last_synth_at": _state["last_synth_at"],
        "last_brief_at": _state["last_brief_at"],
    }


@app.post("/run/synthesize")
async def run_synthesize() -> dict[str, Any]:
    """Trigger an on-demand synth (workflow 10 §6).

    Real wiring requires a configured pipeline (Redis, Chroma, NATS, etc.).
    The default deployment binds the pipeline at startup; in tests we leave
    it unset and surface a 503 so the route is exercised.
    """
    pipeline = _state.get("pipeline")
    if pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline not configured")
    result = await pipeline.run()
    _state["last_synth_at"] = str(result.digest.issued_at)
    _state["last_brief_at"] = str(result.brief.issued_at)
    return {
        "status": "ok",
        "events": len(result.accepted_events),
        "dropped_hash": result.dropped_hash,
        "dropped_semantic": result.dropped_semantic,
    }

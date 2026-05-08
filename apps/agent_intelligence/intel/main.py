"""FastAPI service for the Intelligence agent (workflow 10 §6).

v2.5 T1.3 — `build_pipeline(config)` is the deterministic factory that
binds the IntelPipeline at startup. `/health/deep` runs a 1-doc dry-run
through the pipeline so a `docker compose up agent_intelligence` followed
by an immediate request to `/run/synthesize` returns 200 in < 30 s.

Tests can leave the pipeline unbound by not setting `INTEL_AUTOSTART=1`.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from . import sources as sources_mod
from .factory import IntelConfig, build_pipeline

log = logging.getLogger(__name__)
SERVICE = "agent_intelligence"
PORT = int(os.environ.get("PORT", "8081"))

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")

_state: dict[str, Any] = {
    "last_synth_at": None,
    "last_brief_at": None,
    "feeds_active": 0,
    "pipeline": None,
    "pipeline_built_at": None,
}


def set_pipeline(pipeline: Any) -> None:
    """Tests + the trading-room DAG (T2.x) bind the pipeline directly.

    Used instead of env-driven autostart for unit + integration tests.
    """
    _state["pipeline"] = pipeline


@app.on_event("startup")
async def _startup() -> None:
    sources_path = os.environ.get("INTEL_SOURCES_PATH")
    if sources_path and Path(sources_path).exists():
        try:
            srcs = sources_mod.load_sources(sources_path)
            _state["feeds_active"] = len(srcs)
        except (OSError, ValueError) as exc:
            log.warning("failed to load sources at %s: %s", sources_path, exc)

    if os.environ.get("INTEL_AUTOSTART") != "1":
        return

    config = IntelConfig.from_env()
    try:
        pipeline = build_pipeline(config)
    except Exception as exc:
        # Fail-loud at boot: surface in /health rather than silently 503-ing.
        log.exception("intel pipeline failed to build at startup: %s", exc)
        return
    _state["pipeline"] = pipeline
    _state["pipeline_built_at"] = config.built_at.isoformat()
    _state["feeds_active"] = max(_state["feeds_active"], len(config.sources))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE,
        "feeds_active": _state["feeds_active"],
        "last_synth_at": _state["last_synth_at"],
        "last_brief_at": _state["last_brief_at"],
        "pipeline_bound": _state.get("pipeline") is not None,
    }


@app.get("/health/deep")
async def health_deep() -> dict[str, Any]:
    """Smoke a one-doc run through the pipeline.

    Used by `docker compose up agent_intelligence` smoke check + the
    weekly DR drill. Distinct from `/health` so liveness probes stay
    cheap; this one is opt-in.
    """
    pipeline = _state.get("pipeline")
    if pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline not bound")
    try:
        result = await pipeline.run()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"pipeline run failed: {exc}") from exc
    return {
        "status": "ok",
        "service": SERVICE,
        "events_accepted": len(result.accepted_events),
        "dropped_hash": result.dropped_hash,
        "dropped_semantic": result.dropped_semantic,
    }


@app.post("/run/synthesize")
async def run_synthesize() -> dict[str, Any]:
    """Trigger an on-demand synth (workflow 10 §6)."""
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

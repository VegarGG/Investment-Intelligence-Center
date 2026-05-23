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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from llm_client.bootstrap import lifespan_bootstrap

from . import sources as sources_mod
from .factory import IntelConfig, build_pipeline

log = logging.getLogger(__name__)
SERVICE = "agent_intelligence"
PORT = int(os.environ.get("PORT", "8081"))

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


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """D7.1 §H0.2 — optional-mode router bootstrap. Ingest (RSS / GDELT /
    dedupe / embeddings) doesn't need an LLM, but ``/run/synthesize`` and
    summary endpoints do. Gate LLM-bound paths on ``current_router()``."""
    lifespan_bootstrap(SERVICE, strict=False)
    await _startup_pipeline()
    yield


app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0", lifespan=_lifespan)


async def _startup_pipeline() -> None:
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


@app.post("/run/pull")
async def run_pull(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """P2.9 — partial pull from a single source class (rss / gdelt / macro).

    The orchestrator's `intel_rss_pull` / `intel_gdelt_pull` /
    `intel_macro_pull` cron DAGs call this so the heartbeat pulls don't
    drag the whole synth pipeline. Implemented as a thin shim over
    `pipeline.run()` today; will split into per-source iterators when
    rate-limit budgets diverge enough to matter (see plan §6.2).
    """
    pipeline = _state.get("pipeline")
    if pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline not configured")

    source = (payload or {}).get("source") or "rss"
    result = await pipeline.run()
    accepted_ids = [getattr(e, "id", str(i)) for i, e in enumerate(result.accepted_events)]
    response: dict[str, Any] = {
        "status": "ok",
        "source": source,
        "accepted_event_ids": accepted_ids,
        "events": len(result.accepted_events),
        "dropped_hash": result.dropped_hash,
        "dropped_semantic": result.dropped_semantic,
    }
    if source == "macro":
        # Macro pulls don't go through dedupe, surface the series list.
        macro = getattr(pipeline, "macro", None)
        try:
            from datetime import UTC, datetime

            releases = await macro.fetch(datetime.now(UTC)) if macro else []
        except Exception as exc:  # noqa: BLE001 — heartbeat must not error
            log.warning("macro pull failed: %s", exc)
            releases = []
        response["series"] = [r.series for r in releases]
    return response


@app.get("/api/geo/events")
async def geo_events(window: str = "24h", themes: str | None = None) -> dict[str, Any]:
    """P5.4 — windowed geo-events query for the map dashboard.

    ``window`` accepts ``Nh`` / ``Nm`` / ``Nd`` (e.g. ``24h``). ``themes``
    is a comma-separated allow-list (e.g. ``ECON,TAX``); matching uses
    ``LIKE ':theme%'``. Result is paginated via simple ``LIMIT 10000``
    so the JSON response stays under ~10 MB on the wire.
    """
    from datetime import UTC, datetime, timedelta

    seconds = _parse_window(window)
    since = datetime.now(UTC) - timedelta(seconds=seconds)
    theme_filters = [t.strip() for t in (themes or "").split(",") if t.strip()]

    sm = _state.get("geo_sessionmaker")
    if sm is None:
        # Allow the dashboard to render an empty map in dev installs.
        return {"window": window, "since": since.isoformat(), "events": []}
    from sqlalchemy import text

    sql_base = (
        "SELECT event_id::text AS event_id, ts, lat, lon, theme, tone, "
        "src_url, place "
        "FROM lake.geo_events "
        "WHERE ts >= :since "
    )
    params: dict[str, Any] = {"since": since}
    if theme_filters:
        sql_base += "AND (" + " OR ".join(
            f"theme LIKE :t{i} || '%'" for i in range(len(theme_filters))
        ) + ") "
        for i, t in enumerate(theme_filters):
            params[f"t{i}"] = t
    sql_base += "ORDER BY ts DESC LIMIT 10000"

    async with sm() as session:  # type: ignore[operator]
        res = await session.execute(text(sql_base), params)
        rows = res.all()
    return {
        "window": window,
        "since": since.isoformat(),
        "themes": theme_filters,
        "events": [
            {
                "event_id": r.event_id,
                "ts": r.ts.isoformat(),
                "lat": r.lat,
                "lon": r.lon,
                "theme": r.theme,
                "tone": r.tone,
                "src_url": r.src_url,
                "place": r.place,
            }
            for r in rows
        ],
    }


def _parse_window(window: str) -> int:
    if not window:
        return 24 * 3600
    unit = window[-1].lower()
    try:
        n = int(window[:-1])
    except ValueError:
        return 24 * 3600
    if unit == "h":
        return n * 3600
    if unit == "m":
        return n * 60
    if unit == "d":
        return n * 86400
    return 24 * 3600


@app.websocket("/api/stream/geo_events")
async def geo_events_stream(ws: WebSocket) -> None:
    """D9 §5.6 — WebSocket fanout for the LiveMap dashboard.

    Streams new rows from ``lake.geo_events`` to connected clients. MVP
    implementation polls every 5 s using ``ts`` as a monotonic cursor
    (TimescaleDB hypertable, so the bounded scan is cheap). Production
    should swap to a NATS subscription on the intel-publish subject;
    deferred to D9 V3 once the publish path is real.
    """
    await ws.accept()
    sm = _state.get("geo_sessionmaker")
    if sm is None:
        # No DB wired (dev mode without INTEL_AUTOSTART). Hold the
        # connection open so the client renders "stream open" rather
        # than reconnecting in a tight loop, but emit nothing.
        try:
            while True:
                await asyncio.sleep(60)
        except WebSocketDisconnect:
            return

    from datetime import UTC, datetime

    from sqlalchemy import text

    # Cursor starts at "now" so we only stream new rows, not history.
    cursor = datetime.now(UTC)
    sql = (
        "SELECT event_id::text AS event_id, ts, lat, lon, theme, tone, "
        "src_url, place "
        "FROM lake.geo_events WHERE ts > :cursor ORDER BY ts ASC LIMIT 500"
    )

    try:
        while True:
            async with sm() as session:  # type: ignore[operator]
                res = await session.execute(text(sql), {"cursor": cursor})
                rows = res.all()
            for r in rows:
                cursor = max(cursor, r.ts)
                await ws.send_json(
                    {
                        "event_id": r.event_id,
                        "ts": r.ts.isoformat(),
                        "lat": r.lat,
                        "lon": r.lon,
                        "theme": r.theme,
                        "tone": r.tone,
                        "src_url": r.src_url,
                        "place": r.place,
                    }
                )
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return


@app.post("/run/context")
async def run_context(payload: dict[str, Any]) -> dict[str, Any]:
    """P2.7 — return an ``intel.context.v1`` for a single ticker."""
    from .context import build_context, from_events

    ticker = (payload or {}).get("ticker")
    if not ticker:
        raise HTTPException(status_code=400, detail="missing 'ticker'")
    window_hours = int((payload or {}).get("window_hours", 24))
    pipeline = _state.get("pipeline")
    if pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline not configured")
    # The list-event-store path is the canonical context source in
    # in-memory test mode; production switches to a Postgres-backed query.
    store = getattr(pipeline, "event_store", None)
    events = list(getattr(store, "rows", {}).values()) if store else []
    ctx = await build_context(
        ticker,
        query=from_events(events),
        window_hours=window_hours,
    )
    return ctx.model_dump(by_alias=True, mode="json")

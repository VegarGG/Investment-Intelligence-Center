"""Orchestrator FastAPI app — workflow 06.

Wires triggers (cron + NATS + HTTP) into the DAG registry, exposes the
/health and /run endpoints, and emits ops.heartbeat.v1 every 60 s.

The actual cron + NATS subscription startup is gated by env so unit tests
can import this module without touching the network. Set
ORCH_AUTOSTART=1 to enable scheduler + NATS wiring at import time.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import ulid
from fastapi import FastAPI, HTTPException

from .execute.runner import DagResult, execute
from .execute.sla import with_sla_timeout
from .plan.morning_brief import build_dag, make_initial_state
from .plan.registry import lookup, register
from .state.idempotency import (
    IdempotencyStore,
    InMemoryIdempotencyStore,
    with_idempotency,
)
from .triggers.types import Trigger

log = logging.getLogger(__name__)

SERVICE = "orchestrator"
PORT = int(os.environ.get("PORT", "8080"))

# Process-wide state — populated by lifespan and overridable in tests.
_idem_store: IdempotencyStore = InMemoryIdempotencyStore()
_started_at = time.time()
_last_completed: DagResult[Any] | None = None
_active_dags: dict[str, dict[str, Any]] = {}
_heartbeat_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    if os.environ.get("ORCH_AUTOSTART") == "1":
        await _bootstrap()
    yield


app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0", lifespan=_lifespan)


# ---- triggers / DAG dispatch ----------------------------------------------
async def route(trigger: Trigger) -> Any:
    """Single funnel: every trigger looks up its DAG and runs it under
    the idempotency cache."""
    dag_id = trigger.name.split(":", 1)[-1]
    entry = lookup(trigger.name)
    if entry is None:
        log.info("no DAG registered for trigger=%s — dropping", trigger.name)
        return None

    fired_at_iso = trigger.fired_at.isoformat(timespec="minutes")

    async def _run() -> Any:
        trace_id = str(ulid.ULID())
        _active_dags[trace_id] = {
            "dag_id": dag_id,
            "started_at": datetime.now().isoformat(),
            "trigger": trigger.name,
        }
        try:
            return await entry({"trigger": trigger, "trace_id": trace_id})
        finally:
            _active_dags.pop(trace_id, None)

    return await with_idempotency(
        _idem_store,
        dag_id=dag_id,
        trigger_kind=trigger.kind,
        trigger_at=fired_at_iso,
        force=trigger.force,
        runner=_run,
    )


def register_default_dags(client: Any) -> None:
    """Wire the canonical DAGs into the registry — called from main() at boot.

    Tests may build their own client (e.g., StubAgentClient) and call this
    explicitly before invoking route()."""

    from .plan.auxiliary_dags import (
        _initial,
        build_backtest_fill_event_dag,
        build_evening_recap_dag,
        build_hourly_intel_dag,
        build_intel_digest_event_dag,
        build_intel_gdelt_pull_dag,
        build_intel_macro_pull_dag,
        build_intel_rss_pull_dag,
        build_midday_pulse_dag,
        build_ops_alert_event_dag,
        build_weekly_eval_dag,
    )

    async def _morning_brief(ctx: dict[str, Any]) -> DagResult[Any]:
        global _last_completed
        graph = build_dag(client)
        state = make_initial_state(trace_id=ctx["trace_id"])
        result = await execute(
            graph,
            state,
            trace_id=state.trace_id,
            sla_runner=with_sla_timeout,
        )
        _last_completed = result
        return result

    register("cron:morning_brief", _morning_brief)
    register("http:morning_brief", _morning_brief)

    def _make_simple_runner(builder):
        async def _run(ctx: dict[str, Any]) -> DagResult[Any]:
            global _last_completed
            graph = builder(client)
            state = _initial(trace_id=ctx["trace_id"])
            result = await execute(
                graph,
                state,
                trace_id=state.trace_id,
                sla_runner=with_sla_timeout,
            )
            _last_completed = result
            return result

        return _run

    # v2.5 T1.5 — close the silent-drop surface for cron entries.
    midday = _make_simple_runner(build_midday_pulse_dag)
    evening = _make_simple_runner(build_evening_recap_dag)
    hourly = _make_simple_runner(build_hourly_intel_dag)
    weekly = _make_simple_runner(build_weekly_eval_dag)
    register("cron:midday_check", midday)
    register("http:midday_check", midday)
    register("cron:evening_recap", evening)
    register("http:evening_recap", evening)
    register("cron:hourly_intel", hourly)
    register("http:hourly_intel", hourly)
    register("cron:weekly_eval", weekly)
    register("http:weekly_eval", weekly)

    # P2.9 — fine-grained intel pulls
    rss_pull = _make_simple_runner(build_intel_rss_pull_dag)
    gdelt_pull = _make_simple_runner(build_intel_gdelt_pull_dag)
    macro_pull = _make_simple_runner(build_intel_macro_pull_dag)
    register("cron:intel_rss_pull", rss_pull)
    register("http:intel_rss_pull", rss_pull)
    register("cron:intel_gdelt_pull", gdelt_pull)
    register("http:intel_gdelt_pull", gdelt_pull)
    register("cron:intel_macro_pull", macro_pull)
    register("http:intel_macro_pull", macro_pull)

    # v2.5 T1.5 — close the silent-drop surface for NATS subjects.
    intel_event = _make_simple_runner(build_intel_digest_event_dag)
    fill_event = _make_simple_runner(build_backtest_fill_event_dag)
    ops_event = _make_simple_runner(build_ops_alert_event_dag)
    register("event:intel.digest.v1", intel_event)
    register("event:backtest.fill.v1", fill_event)
    register("event:ops.alert.v1", ops_event)

    # P2.11 — wake the trading-room DAG on intel.event.high_impact.v1.
    # The trading_room DAG itself owns the triage gate + fan-out + board.
    from .plan.trading_room import build_trading_room_dag, make_initial_state as _tr_initial

    async def _trading_room_event(ctx: dict[str, Any]) -> DagResult[Any]:
        global _last_completed
        graph = build_trading_room_dag(client)
        state = _tr_initial(
            trigger_event=ctx.get("payload") or {},
            trace_id=ctx["trace_id"],
        )
        result = await execute(
            graph,
            state,
            trace_id=state.trace_id,
            sla_runner=with_sla_timeout,
        )
        _last_completed = result
        return result

    register("event:intel.event.high_impact.v1", _trading_room_event)
    # P5.5 — geo clusters route through the same trading-room DAG; the
    # triage gate treats them as high-impact context.
    register("event:intel.event.geo_cluster.v1", _trading_room_event)


# ---- HTTP endpoints --------------------------------------------------------
@app.post("/run/{dag_id}")
async def kick(dag_id: str, body: dict[str, Any] | None = None, force: bool = False) -> Any:
    trigger = Trigger(
        kind="http",
        name=f"http:{dag_id}",
        fired_at=datetime.now(),
        payload=body or {},
        force=force,
    )
    result = await route(trigger)
    if result is None:
        raise HTTPException(status_code=404, detail=f"no DAG registered for {dag_id}")
    if isinstance(result, DagResult):
        return {
            "dag_id": result.dag_id,
            "trace_id": result.trace_id,
            "ok": result.ok,
            "nodes": [
                {
                    "name": n.name,
                    "ok": n.ok,
                    "duration_s": round(n.duration_s, 3),
                    "timed_out": n.timed_out,
                    "error": n.error,
                }
                for n in result.nodes
            ],
        }
    return result


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "service": SERVICE,
        "uptime_s": int(time.time() - _started_at),
        "active_dags": list(_active_dags.values()),
        "last_completed": (
            {
                "dag_id": _last_completed.dag_id,
                "trace_id": _last_completed.trace_id,
                "ok": _last_completed.ok,
                "node_count": len(_last_completed.nodes),
            }
            if _last_completed is not None
            else None
        ),
    }


# ---- legacy: keep the Phase-0 stub for backward-compat tests --------------
async def process(event: dict[str, Any]) -> dict[str, Any]:
    return {"received": event.get("id"), "service": SERVICE}


# ---- bootstrap -------------------------------------------------------------
async def _bootstrap() -> None:
    """Production startup — only runs when ORCH_AUTOSTART=1.

    Wires:
      - APScheduler with the §2.1 cron jobs
      - NATS subscriptions to the §6.1 subjects
      - Real Redis-backed idempotency store
      - HttpxAgentClient pointing at each agent's /run
    """
    global _idem_store

    from redis import asyncio as aioredis

    from .plan.agent_client import HttpxAgentClient
    from .triggers.cron import build_scheduler
    from .triggers.nats_events import ORCH_SUBSCRIPTIONS, make_handler

    redis_client: Any = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
    )
    _idem_store = redis_client  # protocol satisfied: SET NX EX

    from .plan.personas import list_persona_slugs

    base_urls: dict[str, str] = {
        "agent_intelligence": "http://agent_intelligence:8081",
        "agent_fundamental": "http://agent_fundamental:8082",
        "agent_quant": "http://agent_quant:8083",
        "agent_secretary": "http://agent_secretary:8086",
    }
    for slug in list_persona_slugs():
        base_urls[f"agent_persona.{slug}"] = "http://agent_persona:8084"
    client = HttpxAgentClient(base_urls)
    register_default_dags(client)

    scheduler = build_scheduler(route)
    scheduler.start()

    # NATS subscriptions are best-effort at boot — log if NATS is not yet up.
    try:
        from data_bus.client import connect, jetstream
        from data_bus.subscribe import subscribe

        nc = await connect()
        js = await jetstream(nc)
        for subject, durable in ORCH_SUBSCRIPTIONS:
            await subscribe(js, subject, durable, make_handler(subject, route))
    except Exception as exc:
        log.warning("NATS subscriptions deferred — connect failed: %s", exc)

    # Heartbeat task — keep a strong ref so the loop's weak refset doesn't GC it mid-flight.
    global _heartbeat_task
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())


async def _heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(60)
        log.info(
            "heartbeat: orchestrator up=%ds active_dags=%d",
            int(time.time() - _started_at),
            len(_active_dags),
        )

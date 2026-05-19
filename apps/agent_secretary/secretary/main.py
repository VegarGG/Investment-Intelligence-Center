"""FastAPI service for the Secretary agent (workflow 15 §6 / P6).

P6 turns this from a one-way notification sink into a leader-router:
  - Outbound dispatcher to any agent in the registry.
  - Conversational planner LLM that turns natural language into RPCs.
  - Per-user prefs (mute, tone, push frequency) backed by lake.user_prefs.
  - Conversation memory (lake.secretary_thread).
  - /chat, /rerun, /prefs endpoints alongside the existing inbound surface.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request

from .agents import HttpxAgentClient, StubAgentClient
from .auth import is_allowed
from .inbound.alertmanager import (
    BadAlertmanagerPayload,
    parse_payload,
    render_all,
)
from .inbound.slash_commands import UnknownSlash, dispatch
from .inbound.wecom_callback import verify
from .memory import InMemoryThreadStore, PostgresThreadStore
from .planner import plan as planner_plan
from .prefs import InMemoryPrefStore, PostgresPrefStore

log = logging.getLogger(__name__)
SERVICE = "agent_secretary"
PORT = int(os.environ.get("PORT", "8086"))
WECOM_TOKEN = os.environ.get("WECOM_TOKEN", "stub-token")

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")


def _init_agents():
    if os.environ.get("SECRETARY_AGENT_BACKEND", "http").lower() == "stub":
        return StubAgentClient()
    return HttpxAgentClient.from_env()


def _init_prefs():
    if os.environ.get("SECRETARY_PREFS_BACKEND", "memory").lower() == "postgres":
        return PostgresPrefStore.from_env()
    return InMemoryPrefStore()


def _init_thread():
    if os.environ.get("SECRETARY_THREAD_BACKEND", "memory").lower() == "postgres":
        return PostgresThreadStore.from_env()
    return InMemoryThreadStore()


agents = _init_agents()
prefs = _init_prefs()
threads = _init_thread()


def set_agents(client) -> None:
    global agents
    agents = client


def set_prefs(store) -> None:
    global prefs
    prefs = store


def set_thread_store(store) -> None:
    global threads
    threads = store


# ---- basic surface ----------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE}


# ---- prefs (P6.4) -----------------------------------------------------------
@app.get("/prefs/{user_id}")
async def get_prefs(user_id: str) -> dict[str, Any]:
    return {"user_id": user_id, "prefs": await prefs.all_for(user_id)}


@app.put("/prefs/{user_id}/{key}")
async def set_pref(user_id: str, key: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    value = body.get("value")
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="missing 'value'")
    ttl = body.get("ttl_seconds")
    await prefs.set(user_id, key, value, ttl_seconds=int(ttl) if ttl else None)
    return {"ok": True, "user_id": user_id, "key": key}


# ---- /chat (P6.3) -----------------------------------------------------------
@app.post("/chat")
async def chat(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="missing 'text'")
    user_id = str(body.get("user_id", "anon"))
    thread_id = str(body.get("thread_id") or uuid4())
    trace_id = str(body.get("trace_id") or uuid4())

    await threads.append(thread_id=thread_id, role="user", content=text, trace_id=trace_id)

    history = await threads.last_n(thread_id, n=20)
    context_turns = [{"role": t.role, "content": t.content} for t in history[:-1]]

    steps = await planner_plan(text, context_turns=context_turns)

    results: list[dict[str, Any]] = []
    for step in steps:
        out = await agents.call(step.caller, step.endpoint, step.args)
        results.append(
            {"caller": step.caller, "endpoint": step.endpoint, "args": step.args, "result": out}
        )

    answer = _stitch_answer(text, results)
    await threads.append(
        thread_id=thread_id, role="assistant", content=answer, trace_id=trace_id
    )
    return {
        "thread_id": thread_id,
        "trace_id": trace_id,
        "user_id": user_id,
        "steps": [
            {"caller": s.caller, "endpoint": s.endpoint, "args": s.args} for s in steps
        ],
        "results": results,
        "answer": answer,
    }


def _stitch_answer(text: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return f"(no agents dispatched for: {text})"
    lines = [f"Resolved {len(results)} agent call(s):"]
    for r in results:
        lines.append(f"- {r['caller']} {r['endpoint']} → {r['result']}")
    return "\n".join(lines)


# ---- /rerun (P6.6) ----------------------------------------------------------
@app.post("/rerun")
async def rerun(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    agent = str(body.get("agent", ""))
    if not agent:
        raise HTTPException(status_code=400, detail="missing 'agent'")
    override = body.get("override_signals") or {}
    if not isinstance(override, dict):
        raise HTTPException(status_code=400, detail="'override_signals' must be object")
    out = await agents.call(agent, "/run/rerun", override)
    return {"agent": agent, "result": out}


# ---- /run/* — real composition (P6.7) ---------------------------------------
@app.post("/run/morning_brief")
async def run_morning_brief() -> dict[str, Any]:
    digest = await agents.call("agent_intelligence", "/run/synthesize", {})
    advice = await agents.call("orchestrator", "/run/morning_brief", {})
    rendered = _compose_brief(
        title="Morning brief",
        digest=digest,
        advice=advice,
        when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return {"status": "ok", "kind": "morning_brief", "markdown": rendered}


@app.post("/run/midday_check")
async def run_midday_check() -> dict[str, Any]:
    digest = await agents.call("agent_intelligence", "/run/pull", {"source": "rss"})
    rendered = _compose_brief(
        title="Midday check",
        digest=digest,
        advice=None,
        when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return {"status": "ok", "kind": "midday_check", "markdown": rendered}


@app.post("/run/evening_recap")
async def run_evening_recap() -> dict[str, Any]:
    book = await agents.call("agent_backtest", "/run/daily_mtm", {})
    rendered = _compose_brief(
        title="Evening recap",
        digest=None,
        advice=book,
        when=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return {"status": "ok", "kind": "evening_recap", "markdown": rendered}


def _compose_brief(
    *,
    title: str,
    digest: dict[str, Any] | None,
    advice: dict[str, Any] | None,
    when: str,
) -> str:
    """Cheap deterministic composition. The LLM-driven version routes
    through the `secretary.brief.morning` caller (P0 + P6 follow-up)."""
    lines = [f"# {title} — {when}"]
    if digest:
        lines.append("")
        lines.append("## Intel")
        lines.append(f"- events={digest.get('events', 0)}")
    if advice:
        lines.append("")
        lines.append("## Advice")
        lines.append(f"- payload={advice}")
    return "\n".join(lines)


# ---- leaderboard / wecom / alertmanager surface (legacy) --------------------
@app.get("/leaderboard")
async def leaderboard() -> str:
    return "Latest leaderboard:\n_(populated when backtester emits)_"


@app.get("/notifier/wecom/callback")
async def wecom_verify(
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
) -> str:
    if not verify(token=WECOM_TOKEN, timestamp=timestamp, nonce=nonce, msg_signature=msg_signature):
        raise HTTPException(status_code=403, detail="bad signature")
    return echostr


@app.post("/notifier/wecom/callback")
async def wecom_inbound(request: Request) -> dict[str, Any]:
    user_id = request.headers.get("X-WeCom-UserId", "")
    if not is_allowed(user_id):
        return {"status": "ignored"}
    body = (await request.body()).decode("utf-8", errors="replace")
    try:
        result = dispatch(body)
        await _apply_slash_side_effects(user_id=user_id, command=result.command, args=result.args)
        return {"status": "ok", "command": result.command, "body": result.body}
    except UnknownSlash:
        return {"status": "unknown_slash"}
    except ValueError:
        return {"status": "ignored"}


@app.post("/notifier/alertmanager")
async def alertmanager_webhook(request: Request) -> dict[str, Any]:
    """Workflow 30 §6.5 — Alertmanager → secretary.notify.v1 bridge."""
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    try:
        alerts = parse_payload(payload)
    except BadAlertmanagerPayload as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notifications = render_all(alerts)
    return {
        "status": "ok",
        "notifications": [
            {"severity": n.severity, "channel_hint": n.channel_hint} for n in notifications
        ],
    }


async def _apply_slash_side_effects(
    *, user_id: str, command: str, args: tuple[str, ...]
) -> None:
    """P6.4 — make `/quiet` and `/tone` actually mutate user prefs."""
    if command == "quiet":
        try:
            minutes = int(args[0]) if args else 30
        except ValueError:
            minutes = 30
        until = datetime.now(UTC)
        await prefs.set(
            user_id,
            "mute_until",
            until.isoformat(),
            ttl_seconds=minutes * 60,
        )
        return
    if command == "tone":
        tone = args[0] if args else "conv"
        await prefs.set(user_id, "tone", tone)
        return

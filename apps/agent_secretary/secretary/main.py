"""FastAPI service for the Secretary agent (workflow 15 §6)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from .auth import is_allowed
from .inbound.slash_commands import UnknownSlash, dispatch
from .inbound.wecom_callback import verify

SERVICE = "agent_secretary"
PORT = int(os.environ.get("PORT", "8086"))
WECOM_TOKEN = os.environ.get("WECOM_TOKEN", "stub-token")

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE}


@app.post("/run/morning_brief")
async def run_morning_brief() -> dict[str, Any]:
    return {"status": "queued"}


@app.post("/run/midday_check")
async def run_midday_check() -> dict[str, Any]:
    return {"status": "queued"}


@app.post("/run/evening_recap")
async def run_evening_recap() -> dict[str, Any]:
    return {"status": "queued"}


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
        return {"status": "ok", "command": result.command, "body": result.body}
    except UnknownSlash:
        return {"status": "unknown_slash"}
    except ValueError:
        return {"status": "ignored"}

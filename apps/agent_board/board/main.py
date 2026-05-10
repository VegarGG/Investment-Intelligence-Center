"""FastAPI service for the Investment Board (v2.5 N3.3 / T2.4)."""

from __future__ import annotations

import logging
import os
from typing import Any

import featureflags.registry  # noqa: F401  ensure canonical flags are registered
from fastapi import FastAPI
from featureflags import flag
from schema.plan import PlanV1

from .bull_bear import debate
from .chair import synthesize_decision
from .persist import board_decision_to_advice
from .risk_panel import deliberate

log = logging.getLogger(__name__)

SERVICE = "agent_board"
PORT = int(os.environ.get("PORT", "8088"))

app = FastAPI(title=f"iic.{SERVICE}", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE,
        "flag_enabled": flag("trading_room.investment_board.enabled"),
    }


@app.post("/decide")
async def decide(request: dict[str, Any]) -> dict[str, Any]:
    """Run the Bull/Bear → Risk → Chair pipeline for one trigger event.

    Request shape:
        {"trigger_event_id": "...", "plans": [<PlanV1 dump>...], "persist": false}

    When ``persist=true`` (and the flag is on) the BoardDecisionV1 is
    appended to ``lake.advice`` under ``agent='board'`` and the row hash
    returned. When false (default for tests) the decision is only
    returned in the response body.
    """

    if not flag("trading_room.investment_board.enabled"):
        return {"status": "skipped", "reason": "flag_disabled"}

    plans = [PlanV1.model_validate(p) for p in request.get("plans") or []]
    if not plans:
        return {"status": "error", "reason": "no_plans"}

    trigger_event_id = str(request.get("trigger_event_id") or "")

    bull_bear_transcript = await debate(plans)
    risk_transcript = await deliberate(plans)
    decision = await synthesize_decision(
        trigger_event_id=trigger_event_id,
        plans=plans,
        bull_bear=bull_bear_transcript,
        risk=risk_transcript,
    )

    response: dict[str, Any] = {
        "status": "ok",
        "decision": decision.model_dump(mode="json", by_alias=True),
        "degraded": bool(bull_bear_transcript.degraded or risk_transcript.degraded),
    }

    if request.get("persist"):
        from .persist import persist_decision

        try:
            row_hash = await persist_decision(decision, plans)
            response["persisted_row_hash"] = row_hash.hex()
        except Exception as exc:  # noqa: BLE001 — return failure to caller, don't lose decision
            log.error("board.persist failed: %s", exc)
            response["persisted_row_hash"] = None
            response["persist_error"] = str(exc)
    else:
        # Build the projected AdviceV1 anyway so callers can preview what
        # would have been written; useful for E2E tests.
        response["preview_advice_v1"] = board_decision_to_advice(decision, plans).model_dump(
            mode="json", by_alias=True
        )

    return response

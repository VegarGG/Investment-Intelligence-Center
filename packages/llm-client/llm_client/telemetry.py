"""Per-call telemetry — fire-and-forget write to lake.llm_calls (workflow 03 §11).

If the write fails, log a warning and move on. Telemetry must never fail a
caller's request.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from typing import Protocol

import orjson

from llm_client.types import ChatMessage, ChatResponse, Outcome

log = logging.getLogger(__name__)

# Strong references for fire-and-forget tasks so the event loop's weak ref
# doesn't GC them mid-flight. We discard via task.add_done_callback(remove).
_pending_tasks: set[asyncio.Task[None]] = set()


class TelemetrySink(Protocol):
    async def write(
        self,
        *,
        caller_id: str,
        request: list[ChatMessage],
        response: ChatResponse | None,
        outcome: Outcome,
        error: str | None,
    ) -> None: ...


class NullTelemetrySink:
    """Drop-on-floor sink — useful for unit tests that don't care."""

    async def write(
        self,
        *,
        caller_id: str,
        request: list[ChatMessage],
        response: ChatResponse | None,
        outcome: Outcome,
        error: str | None,
    ) -> None:
        return


class CapturingTelemetrySink:
    """Test sink that records everything in memory."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def write(
        self,
        *,
        caller_id: str,
        request: list[ChatMessage],
        response: ChatResponse | None,
        outcome: Outcome,
        error: str | None,
    ) -> None:
        row: dict[str, object] = {
            "caller_id": caller_id,
            "outcome": outcome,
            "error": error,
            "tier": None,
            "model": None,
            "cost_usd": 0.0,
            "cached": False,
            "fallback_used": False,
        }
        if response is not None:
            row.update(
                tier=response.tier,
                model=response.model,
                cost_usd=response.cost_usd,
                cached=response.cached,
                fallback_used=response.fallback_used,
            )
        self.calls.append(row)


class PostgresTelemetrySink:
    """Production sink — writes one row to lake.llm_calls per call.

    P0.6: every call outcome lands here, including ``error`` /
    ``timeout`` / ``rate_limit`` / ``skipped``. Missing fields default
    to safe zero values so the row schema is uniform.
    """

    def __init__(self, sessionmaker: object) -> None:
        # sessionmaker is a sqlalchemy.ext.asyncio.async_sessionmaker; typed
        # as object so this module imports cleanly without sqlalchemy.
        self._sm = sessionmaker

    async def write(
        self,
        *,
        caller_id: str,
        request: list[ChatMessage],
        response: ChatResponse | None,
        outcome: Outcome,
        error: str | None,
    ) -> None:
        from sqlalchemy import text

        request_canonical = orjson.dumps(
            [m.model_dump() for m in request], option=orjson.OPT_SORT_KEYS
        )
        request_hash = hashlib.sha256(request_canonical).digest()
        if response is not None:
            tier = response.tier
            model = response.model
            pt = response.prompt_tokens
            ct = response.completion_tokens
            cost = response.cost_usd
            latency = response.latency_ms
            cached = response.cached
            fallback = response.fallback_used
            response_hash = hashlib.sha256(response.text.encode()).digest()
        else:
            tier = "flash"
            model = f"no-response:{outcome}"
            pt = 0
            ct = 0
            cost = 0.0
            latency = 0
            cached = False
            fallback = False
            response_hash = hashlib.sha256(b"").digest()
        async with self._sm() as session:  # type: ignore[operator]
            await session.execute(
                text(
                    "INSERT INTO lake.llm_calls ("
                    "  id, caller_id, tier, model, prompt_tokens, completion_tokens, "
                    "  cost_usd, latency_ms, cached, fallback_used, outcome, error, "
                    "  request_hash, response_hash"
                    ") VALUES ("
                    "  :id, :caller_id, :tier, :model, :pt, :ct, "
                    "  :cost, :latency, :cached, :fallback, :outcome, :error, "
                    "  :req_hash, :resp_hash"
                    ")"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "caller_id": caller_id,
                    "tier": tier,
                    "model": model,
                    "pt": pt,
                    "ct": ct,
                    "cost": cost,
                    "latency": latency,
                    "cached": cached,
                    "fallback": fallback,
                    "outcome": outcome,
                    "error": error,
                    "req_hash": request_hash,
                    "resp_hash": response_hash,
                },
            )
            await session.commit()


def fire_and_forget(
    sink: TelemetrySink,
    *,
    caller_id: str,
    request: list[ChatMessage],
    response: ChatResponse | None,
    outcome: Outcome,
    error: str | None,
) -> None:
    """Schedule a telemetry write without awaiting. Errors logged, never raised."""

    async def _write() -> None:
        try:
            await sink.write(
                caller_id=caller_id,
                request=request,
                response=response,
                outcome=outcome,
                error=error,
            )
        except Exception as exc:
            log.warning("telemetry write failed: %s", exc)

    task = asyncio.create_task(_write())
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)

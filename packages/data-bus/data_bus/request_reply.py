"""NATS request-reply substrate (v2.5 T2.0 / B3.1).

Plan §T2.0: a transport-shim so future tick-driven trading-room DAGs can
fan out to agents via NATS request-reply instead of HTTP. The HTTP path
stays as a fallback; new DAGs can ride NATS for tighter latency and
native trace propagation.

This module ships:
- ``nats_call(subject, payload, timeout_s)`` — request-reply with auto
  trace propagation (reads ``payload['trace_id']`` if present, generates
  ULID if not).
- ``register_handler(subject, fn)`` — agent-side handler registration.
  Each agent's ``apps/<svc>/<pkg>/nats_runner.py`` calls this at startup
  to mirror its HTTP ``/run`` endpoint.

The shim is feature-flag gated by ``orchestrator.use_nats_for_agent_calls``
(default off). The matching unit test verifies morning_brief runs
identically with the flag on or off.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import orjson

log = logging.getLogger(__name__)


# Subject convention for agent request-reply. Each agent listens on
# ``iic.agent.<slug>``; the shim publishes to that subject and awaits
# the reply on a per-request inbox.
AGENT_SUBJECT_PREFIX = "iic.agent."


def agent_subject(agent_id: str) -> str:
    """Map ``agent_persona.rogers`` → ``iic.agent.agent_persona.rogers``."""
    return f"{AGENT_SUBJECT_PREFIX}{agent_id}"


# In-memory NATS shim used by tests so they don't need a live broker.
# Production code uses the real `nats-py` client below.
_LOCAL_HANDLERS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {}


def register_handler(
    subject: str,
    handler: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
) -> None:
    """Register a request handler for `subject`.

    Tests call this directly. In production, each agent's `nats_runner.py`
    wraps the real `nats.aio.client` subscription with this shape.
    """
    _LOCAL_HANDLERS[subject] = handler


def clear_handlers_for_test() -> None:
    _LOCAL_HANDLERS.clear()


async def nats_call(
    subject: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Request-reply against `subject`. Generates a trace_id if absent.

    Resolution order:
    1. If a local handler is registered (tests + dev), call it directly.
    2. Otherwise, open a real NATS request-reply.
    """
    if "trace_id" not in payload or not payload["trace_id"]:
        import ulid

        payload = {**payload, "trace_id": str(ulid.ULID())}

    local = _LOCAL_HANDLERS.get(subject)
    if local is not None:
        return await asyncio.wait_for(local(dict(payload)), timeout=timeout_s)

    # Production path — talk to NATS.
    return await _real_nats_call(subject, payload, timeout_s=timeout_s)


async def _real_nats_call(
    subject: str,
    payload: dict[str, Any],
    *,
    timeout_s: float,
) -> dict[str, Any]:
    if os.environ.get("IIC_NATS_REQUEST_REPLY_DISABLED") == "1":
        raise RuntimeError(
            "NATS request-reply disabled by env; flip the feature flag off"
        )
    from data_bus.client import connect

    nc = await connect()
    try:
        body = orjson.dumps(payload)
        msg = await nc.request(subject, body, timeout=timeout_s)
        if not msg.data:
            return {}
        return orjson.loads(msg.data)
    finally:
        await nc.drain()


def make_reply_handler(
    fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
) -> Callable[[Any], Awaitable[None]]:
    """Wrap a handler `fn(payload) -> reply_dict` into a NATS Msg callback.

    Each agent's `nats_runner.py` calls this against its `/run`-shaped
    handler, then `await js.subscribe(subject, cb=cb)`.
    """

    async def _on_msg(msg: Any) -> None:
        try:
            payload = orjson.loads(msg.data) if msg.data else {}
        except orjson.JSONDecodeError:
            await msg.respond(b'{"_error":"bad_payload"}')
            return
        try:
            reply = await fn(payload)
        except Exception as exc:
            log.exception("nats handler raised: %s", exc)
            reply = {"_error": str(exc)}
        await msg.respond(orjson.dumps(reply))

    return _on_msg

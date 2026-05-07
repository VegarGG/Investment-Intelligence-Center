"""publish() — workflow 05 §6 + §8.3.

Enforces the .v\\d+ subject suffix, serializes Pydantic models, sets
Nats-Msg-Id from the idempotency key (60s JetStream dedup window catches
producer retries), and emits an OpenTelemetry span.
"""

from __future__ import annotations

from typing import Any, Protocol

import orjson
from pydantic import BaseModel

from data_bus.subjects import assert_valid_subject, stream_for
from data_bus.tracing import inject_headers, span


class PublishTarget(Protocol):
    """The minimum surface publish() needs from a JetStream context.
    Real impl: nats.js.client.JetStreamContext.publish (returns PubAck);
    test impl: an in-memory recorder."""

    async def publish(
        self,
        subject: str,
        payload: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> Any: ...


def _serialize(payload: BaseModel | dict[str, Any]) -> bytes:
    if isinstance(payload, BaseModel):
        return orjson.dumps(payload.model_dump(by_alias=True, mode="json"))
    return orjson.dumps(payload)


async def publish(
    js: PublishTarget,
    subject: str,
    payload: BaseModel | dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> str:
    """Validate, serialize, trace, send. Returns the message id (idempotency key
    if supplied; the JetStream PubAck stream sequence otherwise)."""
    assert_valid_subject(subject)
    stream_name = stream_for(subject)  # raises if not bound to a stream

    body = _serialize(payload)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if idempotency_key:
        headers["Nats-Msg-Id"] = idempotency_key
    headers = inject_headers(headers)

    with span(
        "nats.publish",
        **{
            "messaging.system": "nats",
            "messaging.destination": subject,
            "messaging.destination_kind": "topic",
            "iic.stream": stream_name,
            "iic.payload_bytes": len(body),
        },
    ):
        ack = await js.publish(subject, body, headers=headers)

    if idempotency_key:
        return idempotency_key
    seq = getattr(ack, "seq", None)
    return f"{stream_name}@{seq}" if seq is not None else stream_name

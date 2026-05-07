"""subscribe() — workflow 05 §6 + §8.3.

Wraps the user handler with ack-on-success / nak-on-exception logic and
OpenTelemetry context restoration. `durable_name` survives consumer
restarts; `queue_group` opts into NATS load-balancing.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from data_bus.exceptions import HandlerError
from data_bus.tracing import attach_context, extract_context, span

if TYPE_CHECKING:
    from nats.aio.msg import Msg
    from nats.js.client import JetStreamContext

log = logging.getLogger(__name__)

Handler = Callable[["Msg"], Awaitable[None]]


@dataclass(slots=True)
class Subscription:
    cancel: Callable[[], Awaitable[None]]


def _wrap_handler(subject: str, handler: Handler) -> Handler:
    async def _wrapped(msg: Msg) -> None:
        # Restore tracing context the producer injected.
        ctx = extract_context(msg.headers or {})
        with (
            attach_context(ctx),
            span(
                "nats.consume",
                **{
                    "messaging.system": "nats",
                    "messaging.destination": subject,
                    "messaging.destination_kind": "topic",
                    "iic.payload_bytes": len(msg.data or b""),
                },
            ),
        ):
            try:
                await handler(msg)
                await msg.ack()
            except Exception as exc:
                log.warning(
                    "subject=%s handler raised: %s — naking for redelivery",
                    subject,
                    exc,
                )
                # nak with redelivery; max_deliver is enforced by the consumer config.
                await msg.nak()
                raise HandlerError(f"handler for {subject} failed: {exc}") from exc

    return _wrapped


async def subscribe(
    js: JetStreamContext,
    subject: str,
    durable_name: str,
    handler: Handler,
    *,
    queue_group: str | None = None,
    max_deliver: int = 5,
) -> Subscription:
    """Workflow 05 §6 — durable JetStream consumer with handler wrapping.

    Convention: durable_name is `<service>.<purpose>` (workflow 05 §11
    risk #3 — collisions form a load-balanced queue group, sometimes a
    foot-gun)."""
    from nats.js.api import ConsumerConfig, DeliverPolicy

    cfg = ConsumerConfig(
        durable_name=durable_name,
        deliver_policy=DeliverPolicy.NEW,
        max_deliver=max_deliver,
        ack_wait=30,
    )
    sub = await js.subscribe(
        subject,
        durable=durable_name,
        queue=queue_group,
        config=cfg,
        cb=_wrap_handler(subject, handler),
    )

    async def _cancel() -> None:
        await sub.unsubscribe()

    return Subscription(cancel=_cancel)


async def consume_one(msg: Msg, handler: Handler, subject: str) -> None:
    """Helper for tests that want to drive the wrapped handler synchronously
    without hitting JetStream."""
    wrapped = _wrap_handler(subject, handler)
    await wrapped(msg)


_unused: Any = None  # silence unused-import warnings when nats stubs are absent

"""NATS async client wrapper with auto-reconnect (workflow 05 §6)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nats.aio.client import Client as NatsClient
    from nats.js.client import JetStreamContext


@lru_cache(maxsize=1)
def _nats_url() -> str:
    return os.environ.get("NATS_URL", "nats://nats:4222")


async def connect() -> NatsClient:
    """Open one NATS connection per process. Caller closes via `await nc.close()`.

    Reconnect: nats-py manages this with `max_reconnect_attempts=-1` so a
    JetStream restart on the host doesn't take down a long-lived consumer.
    """
    import nats

    return await nats.connect(
        _nats_url(),
        name="iic.data_bus",
        max_reconnect_attempts=-1,
        reconnect_time_wait=2.0,
        ping_interval=20,
        max_outstanding_pings=3,
    )


async def jetstream(nc: NatsClient) -> JetStreamContext:
    """JetStream context — owned by caller, lifetime tied to the connection."""
    return nc.jetstream()

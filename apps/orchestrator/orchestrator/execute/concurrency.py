"""Pro-tier concurrency cap (workflow 06 §2.3 + §6.4).

Max 4 in-flight Pro calls system-wide. Implemented as a slot-based
distributed semaphore in Redis: try to claim one of N keys
(`lock:pro_concurrency:1` ... `:N`) via SET NX with TTL; release on exit.

A Redis-less in-memory variant exists for tests.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol, cast

log = logging.getLogger(__name__)

DEFAULT_CAPACITY = int(os.environ.get("ORCH_PRO_CONCURRENCY", "4"))
SLOT_TTL_S = 300  # how long a held slot survives if the holder crashes


class SemaphoreBackend(Protocol):
    """Subset of redis.asyncio.Redis we use — keeps tests light."""

    async def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None: ...

    async def delete(self, *keys: str) -> int: ...


class InMemorySemaphoreBackend:
    """For tests — emulates Redis SET NX semantics."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,  # ttl ignored in-memory
    ) -> bool | None:
        async with self._lock:
            if nx and name in self._store:
                return None
            self._store[name] = value
            return True

    async def delete(self, *keys: str) -> int:
        async with self._lock:
            n = sum(1 for k in keys if k in self._store)
            for k in keys:
                self._store.pop(k, None)
            return n


@asynccontextmanager
async def acquire_pro_slot(
    backend: SemaphoreBackend,
    *,
    capacity: int = DEFAULT_CAPACITY,
    holder: str = "orch",
    poll_interval_s: float = 0.05,
    timeout_s: float = 300.0,
) -> AsyncIterator[int]:
    """Block until one of `capacity` Pro slots is free, then yield the slot id.

    Releases the slot on exit (success or exception).

    holder is recorded as the slot value so an `nats kv` peek shows who's
    holding what — useful when the breaker opens unexpectedly.
    """
    slot_id = await _claim(
        backend, capacity, holder, poll_interval_s=poll_interval_s, timeout_s=timeout_s
    )
    try:
        yield slot_id
    finally:
        await backend.delete(_slot_key(slot_id))


async def _claim(
    backend: SemaphoreBackend,
    capacity: int,
    holder: str,
    *,
    poll_interval_s: float,
    timeout_s: float,
) -> int:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while True:
        for slot in range(1, capacity + 1):
            key = _slot_key(slot)
            ok = await backend.set(key, holder, nx=True, ex=SLOT_TTL_S)
            if ok:
                return slot
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(
                f"could not acquire pro slot within {timeout_s}s "
                f"(capacity={capacity}, all slots held)"
            )
        await asyncio.sleep(poll_interval_s)


def _slot_key(slot: int) -> str:
    return f"lock:pro_concurrency:{slot}"


def from_env() -> SemaphoreBackend:
    """Build the production backend (real Redis) from env. Tests build
    an InMemorySemaphoreBackend directly."""
    from redis import asyncio as aioredis

    url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    client: SemaphoreBackend = cast(SemaphoreBackend, aioredis.from_url(url, decode_responses=True))
    return client

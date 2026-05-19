"""Redis-backed dedupe hash store (P2.2).

Uses ``SET key 1 NX EX <ttl>`` for atomic claim. The Redis client is
``redis.asyncio`` (already a peer dep of the agent images via iic-base).

Configuration from env (``RedisHashStore.from_env()``):
  - ``REDIS_URL``        — e.g. ``redis://iic-redis:6379/0``
  - ``INTEL_DEDUPE_TTL`` — seconds, default ``604800`` (7 days).
"""

from __future__ import annotations

import os

from .hash_gate import DEDUPE_TTL_SECONDS, HashStore


class RedisHashStore(HashStore):
    """Production HashStore backed by Redis with NX/EX claim semantics."""

    __slots__ = ("_client", "_default_ttl")

    def __init__(self, client, *, default_ttl_seconds: int = DEDUPE_TTL_SECONDS) -> None:
        self._client = client
        self._default_ttl = default_ttl_seconds

    @classmethod
    def from_env(cls) -> "RedisHashStore":
        import redis.asyncio as redis  # local import — heavy dep

        url = os.environ.get("REDIS_URL", "redis://iic-redis:6379/0")
        ttl = int(os.environ.get("INTEL_DEDUPE_TTL", str(DEDUPE_TTL_SECONDS)))
        return cls(redis.from_url(url, decode_responses=True), default_ttl_seconds=ttl)

    async def claim(self, key: str, ttl_seconds: int) -> bool:
        # SET key 1 NX EX ttl  →  None when the key already existed.
        ttl = ttl_seconds or self._default_ttl
        ok = await self._client.set(name=key, value="1", nx=True, ex=ttl)
        return bool(ok)

    async def aclose(self) -> None:
        try:
            await self._client.aclose()
        except AttributeError:  # pragma: no cover - older redis-py
            await self._client.close()

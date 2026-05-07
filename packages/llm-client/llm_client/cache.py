"""Redis-backed prompt cache for Flash deterministic callers (workflow 03 §9).

Storage protocol: any backend that implements `CacheStore`. Redis impl is
the production default; an in-memory impl exists for tests.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import orjson

from llm_client.types import ChatMessage, ChatResponse, LlmTier


def cache_key(caller_id: str, tier: LlmTier, messages: list[ChatMessage]) -> str:
    """sha256(caller_id || tier || canonical_json(messages))."""
    canonical = orjson.dumps(
        {"c": caller_id, "t": tier, "m": [m.model_dump() for m in messages]},
        option=orjson.OPT_SORT_KEYS,
    )
    digest = hashlib.sha256(canonical).hexdigest()
    return f"cache:llm:{caller_id}:{digest}"


class CacheStore(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int | None) -> None: ...


class InMemoryCacheStore:
    """For tests. No TTL enforcement (we don't sleep in unit tests)."""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None) -> None:
        self._d[key] = value


class RedisCacheStore:
    """Production cache. Uses the redis.asyncio client passed in by the router."""

    def __init__(self, redis_client: object) -> None:
        # redis_client is a redis.asyncio.Redis — typed as object to keep
        # this module importable without the redis dep at type-check time.
        self._r = redis_client

    async def get(self, key: str) -> str | None:
        result = await self._r.get(key)  # type: ignore[attr-defined]
        return result if result is None or isinstance(result, str) else result.decode()

    async def set(self, key: str, value: str, ttl_seconds: int | None) -> None:
        if ttl_seconds is None:
            await self._r.set(key, value)  # type: ignore[attr-defined]
        else:
            await self._r.set(key, value, ex=ttl_seconds)  # type: ignore[attr-defined]


class PromptCache:
    """Wraps a CacheStore with response (de)serialization."""

    def __init__(self, store: CacheStore) -> None:
        self._store = store

    async def get(
        self, caller_id: str, tier: LlmTier, messages: list[ChatMessage]
    ) -> ChatResponse | None:
        raw = await self._store.get(cache_key(caller_id, tier, messages))
        if raw is None:
            return None
        cached = ChatResponse.model_validate_json(raw)
        return cached.model_copy(update={"cached": True, "cost_usd": 0.0})

    async def set(
        self,
        caller_id: str,
        tier: LlmTier,
        messages: list[ChatMessage],
        response: ChatResponse,
        ttl_seconds: int | None,
    ) -> None:
        await self._store.set(
            cache_key(caller_id, tier, messages),
            response.model_dump_json(),
            ttl_seconds,
        )

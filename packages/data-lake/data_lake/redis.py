"""Redis async cache helpers (workflow 02 §5.8).

KEY PREFIXES (GROUND TRUTH from §5.8):
  dedupe:hash:<sha256>      7d   article dedupe gate
  cache:llm:<route>:<hash>  1h   prompt-result cache (Flash only)
  ratelimit:<provider>:<k>  -    sliding window
  lock:<resource>           60s  redlock-style
  last_seen:<feed_id>       inf  crawler resume cursor
"""

# `redis` (the third-party package) collides with this module name. PEP 328
# absolute imports resolve `from redis import ...` to the top-level package
# even from inside data_lake/redis.py — but be explicit to avoid surprises.
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis  # type: ignore[import]

from data_lake.config import get_config

DEDUPE_TTL = 60 * 60 * 24 * 7  # 7 days
LLM_CACHE_TTL = 60 * 60  # 1 hour
LOCK_TTL = 60  # seconds


@lru_cache(maxsize=1)
def client() -> Redis:
    from redis import asyncio as aioredis  # type: ignore[import]

    cfg = get_config()
    return aioredis.from_url(cfg.redis_url, encoding="utf-8", decode_responses=True)


async def seen_dedupe(content_hash: str) -> bool:
    """Return True if this hash has been seen recently. Marks seen on first call."""
    r = client()
    key = f"dedupe:hash:{content_hash}"
    set_ok = await r.set(key, "1", ex=DEDUPE_TTL, nx=True)
    return not bool(set_ok)


async def llm_cache_get(route: str, prompt_hash: str) -> str | None:
    r = client()
    return await r.get(f"cache:llm:{route}:{prompt_hash}")


async def llm_cache_set(route: str, prompt_hash: str, value: str) -> None:
    r = client()
    await r.set(f"cache:llm:{route}:{prompt_hash}", value, ex=LLM_CACHE_TTL)


async def crawler_cursor_set(feed_id: str, value: str) -> None:
    r = client()
    await r.set(f"last_seen:{feed_id}", value)


async def crawler_cursor_get(feed_id: str) -> str | None:
    r = client()
    return await r.get(f"last_seen:{feed_id}")

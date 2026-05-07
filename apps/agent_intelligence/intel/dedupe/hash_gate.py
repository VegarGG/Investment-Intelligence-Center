"""7-day Redis hash dedupe gate (workflow 10 §5.3 #1).

`sha256(source_id, url|title, event_ts)` → set with TTL. Production uses
Redis (`dedupe:hash:<sha>` per workflow 02 §5.8); tests pass an in-memory
store via the protocol.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Protocol

from ..types import RawEvent

DEDUPE_TTL_SECONDS = 7 * 24 * 3600


class HashStore(Protocol):
    """Minimal SET-IF-NOT-EXISTS surface — Redis or in-memory."""

    async def claim(self, key: str, ttl_seconds: int) -> bool: ...


class InMemoryHashStore:
    """Test backend — set + first-write-wins semantics. No TTL eviction."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    async def claim(self, key: str, ttl_seconds: int) -> bool:
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


def hash_for(event: RawEvent) -> str:
    payload = "|".join(
        [
            event.source_id,
            event.url or event.title,
            _ts(event.event_ts),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ts(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat()


class HashGate:
    """`async accept(event) -> bool` — True when this is the first time we
    saw the (source, url|title, ts) triple within 7 days."""

    def __init__(self, store: HashStore, *, ttl_seconds: int = DEDUPE_TTL_SECONDS) -> None:
        self._store = store
        self._ttl = ttl_seconds

    async def accept(self, event: RawEvent) -> bool:
        key = f"dedupe:hash:{hash_for(event)}"
        return await self._store.claim(key, self._ttl)

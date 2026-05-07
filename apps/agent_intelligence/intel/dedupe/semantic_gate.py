"""Semantic dedupe via cosine threshold over the past 24 h (workflow 10 §5.3 #2).

The production index is ChromaDB `news` collection (bge-m3). We isolate
both the embedder and the index behind small protocols so the unit test
can wire deterministic vectors without spinning up Chroma.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ..types import RawEvent

DEFAULT_THRESHOLD = 0.92
DEFAULT_WINDOW = timedelta(hours=24)

EmbedFn = Callable[[str], Awaitable[list[float]]]


class SemanticIndex(Protocol):
    async def search(
        self, vector: list[float], *, k: int, since: datetime
    ) -> list[tuple[str, float, datetime]]:
        """Return up to k matches: (id, cosine_similarity, indexed_at)."""

    async def insert(self, doc_id: str, vector: list[float], indexed_at: datetime) -> None: ...


class InMemorySemanticIndex:
    """Brute-force cosine search against an in-memory list. Adequate for
    the unit tests; production swaps in a Chroma-backed adapter."""

    def __init__(self) -> None:
        self._docs: list[tuple[str, list[float], datetime]] = []

    async def search(
        self, vector: list[float], *, k: int, since: datetime
    ) -> list[tuple[str, float, datetime]]:
        scored = [
            (doc_id, _cosine(vector, vec), ts) for doc_id, vec, ts in self._docs if ts >= since
        ]
        scored.sort(key=lambda r: r[1], reverse=True)
        return scored[:k]

    async def insert(self, doc_id: str, vector: list[float], indexed_at: datetime) -> None:
        self._docs.append((doc_id, vector, indexed_at))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class SemanticGate:
    """`async accept(event) -> (bool, near_duplicate_id|None)`.

    Returns False (drop) when a sibling within the 24h window has cosine
    similarity > threshold. The near-duplicate id is returned so callers
    can link events instead of inserting orphans.
    """

    def __init__(
        self,
        index: SemanticIndex,
        embed: EmbedFn,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        window: timedelta = DEFAULT_WINDOW,
    ) -> None:
        self._index = index
        self._embed = embed
        self._threshold = threshold
        self._window = window

    async def accept(self, event: RawEvent) -> tuple[bool, str | None]:
        text = f"{event.title}\n\n{event.body}"
        vec = await self._embed(text)
        since = event.ingest_ts.astimezone(UTC) - self._window
        hits = await self._index.search(vec, k=5, since=since)
        if hits and hits[0][1] > self._threshold:
            return False, hits[0][0]
        doc_id = f"{event.source_id}:{event.event_ts.isoformat()}"
        await self._index.insert(doc_id, vec, event.ingest_ts.astimezone(UTC))
        return True, None


def hash_embed(text: str, *, dim: int = 32) -> list[float]:
    """Cheap deterministic embedding for tests — character histogram.

    Identical strings collide perfectly; near-strings score high.
    """
    vec = [0.0] * dim
    for ch in text.lower():
        vec[ord(ch) % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]

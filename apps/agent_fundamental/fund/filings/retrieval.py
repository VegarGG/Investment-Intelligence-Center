"""Retrieval helper for the filings ChromaDB collection (workflow 11 §7).

Production indexes vectors via DeepSeek bge-m3 into Chroma. We expose a
small protocol so unit tests can exercise the section-preference behavior
without spinning up Chroma.
"""

from __future__ import annotations

from typing import Protocol

from ..types import Chunk

PREFERRED_SECTIONS = ("Item 7", "Item 1A", "Item 7A", "Item 1")


class FilingsIndex(Protocol):
    async def query(self, ticker: str, query: str, *, k: int = 8) -> list[Chunk]: ...

    async def add(self, ticker: str, chunks: list[Chunk]) -> None: ...


class InMemoryFilingsIndex:
    """Simple keyword-overlap retriever — boosts preferred sections."""

    def __init__(self) -> None:
        self._by_ticker: dict[str, list[Chunk]] = {}

    async def add(self, ticker: str, chunks: list[Chunk]) -> None:
        self._by_ticker.setdefault(ticker, []).extend(chunks)

    async def query(self, ticker: str, query: str, *, k: int = 8) -> list[Chunk]:
        chunks = self._by_ticker.get(ticker, [])
        terms = {t.lower() for t in query.split() if len(t) > 3}
        scored: list[tuple[float, Chunk]] = []
        for c in chunks:
            text = c.text.lower()
            base = sum(1 for t in terms if t in text)
            boost = 0.5 if c.section in PREFERRED_SECTIONS else 0.0
            score = base + boost
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda r: r[0], reverse=True)
        return [c for _, c in scored[:k]]

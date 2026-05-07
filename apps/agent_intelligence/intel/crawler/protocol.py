"""CrawlerProtocol + an InMemoryCrawler for tests (workflow 10 §5.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Protocol

from ..types import RawEvent, SourceCfg


class CrawlerProtocol(Protocol):
    """All crawler implementations expose `fetch(source) -> async iterator[RawEvent]`.

    Production impls (rss.py, telegram.py, edgar.py, etc.) own per-source
    rate limiting and resume cursors via Redis (`last_seen:<source_id>`).
    """

    def fetch(self, source: SourceCfg) -> AsyncIterator[RawEvent]: ...


class InMemoryCrawler:
    """Test fixture — replays a pre-populated mapping `{source_id: [events]}`.

    Lets the pipeline tests stay deterministic without touching real RSS feeds.
    """

    def __init__(self, events_by_source: dict[str, Iterable[RawEvent]]) -> None:
        self._events = {k: list(v) for k, v in events_by_source.items()}

    async def fetch(self, source: SourceCfg) -> AsyncIterator[RawEvent]:
        for ev in self._events.get(source.id, []):
            yield ev

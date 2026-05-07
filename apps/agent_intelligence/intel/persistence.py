"""Persistence helpers — write Events to lake.events with bias metadata.

Production wires `data_lake.postgres`. We expose a thin protocol so unit
tests can capture writes without a database.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Protocol

from .types import Event


class EventStore(Protocol):
    async def insert(self, event: Event, *, hash_key: str) -> bool:
        """Insert with `ON CONFLICT (hash) DO NOTHING`. Return True when
        a row was actually written."""


class InMemoryEventStore:
    def __init__(self) -> None:
        self._rows: dict[str, Event] = {}

    async def insert(self, event: Event, *, hash_key: str) -> bool:
        if hash_key in self._rows:
            return False
        self._rows[hash_key] = event
        return True

    @property
    def rows(self) -> dict[str, Event]:
        return dict(self._rows)


def event_hash(event: Event) -> str:
    payload = "|".join(
        [
            event.source_id,
            event.url or event.title_en,
            _ts(event.event_ts),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ts(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat()

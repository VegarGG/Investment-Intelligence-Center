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


class PostgresEventStore(EventStore):
    """Production EventStore backed by ``lake.events`` (P2.6).

    Uses ``INSERT ... ON CONFLICT (hash) DO NOTHING`` so the dedupe is
    DB-enforced even if the in-process hash gate misses. Returns True
    when the row was actually written; False on conflict.
    """

    __slots__ = ("_sm",)

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    @classmethod
    def from_env(cls) -> "PostgresEventStore":
        import os

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get(
            "IIC_PG_DSN",
            "postgresql+asyncpg://iic_app@iic-postgres:5432/iic",
        )
        engine = create_async_engine(url, pool_pre_ping=True)
        return cls(async_sessionmaker(engine, expire_on_commit=False))

    async def insert(self, event: Event, *, hash_key: str) -> bool:
        from sqlalchemy import text

        sql = text(
            """
            INSERT INTO lake.events (
                id, ts, source_id, source_region, source_lean,
                title, body, title_en, body_en, lang, sentiment,
                target_assets, url, hash
            ) VALUES (
                :id, :ts, :source_id, :source_region, :source_lean,
                :title, :body, :title_en, :body_en, :lang, :sentiment,
                :target_assets, :url, :hash
            )
            ON CONFLICT (hash) DO NOTHING
            RETURNING id
            """
        )
        params = {
            "id": event.id,
            "ts": event.event_ts,
            "source_id": event.source_id,
            "source_region": event.source_region,
            "source_lean": event.source_lean,
            "title": event.title,
            "body": event.body,
            "title_en": event.title_en,
            "body_en": event.body_en,
            "lang": event.lang,
            "sentiment": event.sentiment,
            "target_assets": list(event.target_assets),
            "url": event.url,
            "hash": hash_key,
        }
        async with self._sm() as session:
            res = await session.execute(sql, params)
            row = res.first()
            await session.commit()
            return row is not None

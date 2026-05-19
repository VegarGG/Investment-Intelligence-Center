"""Persist geocoded events to ``lake.geo_events`` (P5.2).

Used by the GDELT crawler — for each ``RawEvent`` it produces, if the
``raw`` dict carries lat/lon, we also write a row here so the geo
dashboard has the spatial cache it needs.

Decoupled from the GDELT crawler module so other geo feeds (open-street
incident streams, etc.) can plug in later.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any, Protocol

log = logging.getLogger(__name__)


class GeoEventSink(Protocol):
    async def insert(
        self,
        *,
        ts: datetime,
        lat: float | None,
        lon: float | None,
        theme: str | None,
        tone: float | None,
        src_url: str | None,
        urls: list[str] | None,
        place: str | None,
        gkg_id: str | None,
    ) -> bool: ...


class InMemoryGeoEventSink(GeoEventSink):
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def insert(self, **kwargs: Any) -> bool:
        self.rows.append(kwargs)
        return True


class PostgresGeoEventSink(GeoEventSink):
    """Writes one row per geo event to ``lake.geo_events``."""

    __slots__ = ("_sm",)

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    @classmethod
    def from_env(cls) -> "PostgresGeoEventSink":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get(
            "IIC_PG_DSN",
            "postgresql+asyncpg://iic_app@iic-postgres:5432/iic",
        )
        engine = create_async_engine(url, pool_pre_ping=True)
        return cls(async_sessionmaker(engine, expire_on_commit=False))

    async def insert(
        self,
        *,
        ts: datetime,
        lat: float | None,
        lon: float | None,
        theme: str | None,
        tone: float | None,
        src_url: str | None,
        urls: list[str] | None,
        place: str | None,
        gkg_id: str | None,
    ) -> bool:
        from sqlalchemy import text

        sql = text(
            """
            INSERT INTO lake.geo_events (
              ts, lat, lon, theme, tone, src_url, urls, place, gkg_id
            ) VALUES (
              :ts, :lat, :lon, :theme, :tone, :src_url, :urls, :place, :gkg_id
            )
            """
        )
        async with self._sm() as session:  # type: ignore[operator]
            await session.execute(
                sql,
                {
                    "ts": ts,
                    "lat": lat,
                    "lon": lon,
                    "theme": theme,
                    "tone": tone,
                    "src_url": src_url,
                    "urls": urls,
                    "place": place,
                    "gkg_id": gkg_id,
                },
            )
            await session.commit()
        return True


async def write_geo_event_from_raw(
    sink: GeoEventSink,
    raw_event: Any,
) -> bool:
    """Write a `RawEvent` produced by the GDELT crawler. Skips when no
    lat/lon is present."""
    meta = getattr(raw_event, "raw", None) or {}
    lat = meta.get("lat")
    lon = meta.get("lon")
    if lat is None or lon is None:
        return False
    themes = meta.get("themes") or []
    primary_theme = themes[0].split(",", 1)[0] if themes else None
    return await sink.insert(
        ts=getattr(raw_event, "event_ts", datetime.now(UTC)),
        lat=lat,
        lon=lon,
        theme=primary_theme,
        tone=meta.get("tone"),
        src_url=getattr(raw_event, "url", None),
        urls=None,
        place=None,
        gkg_id=meta.get("gkg_record_id"),
    )

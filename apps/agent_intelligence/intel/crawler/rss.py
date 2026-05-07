"""RSS / Atom crawler (workflow 10 §5.2).

Real impl uses feedparser. Heavy network work is gated by a small async
helper so we can unit-test the parser without the network. The transport
itself is injected — `fetch_url` callable returns the raw feed bytes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from ..types import RawEvent, SourceCfg

UrlFetcher = Callable[[str], Awaitable[bytes]]


async def _httpx_fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


class RSSCrawler:
    """Parses RSS/Atom feeds via feedparser. The transport is pluggable so
    tests pass canned XML without HTTP."""

    def __init__(self, fetch_url: UrlFetcher | None = None) -> None:
        self._fetch = fetch_url or _httpx_fetch

    async def fetch(self, source: SourceCfg) -> AsyncIterator[RawEvent]:
        if not source.url:
            return
        try:
            blob = await self._fetch(source.url)
        except (httpx.HTTPError, OSError):
            return  # crawler errors are best-effort; pipeline continues
        for ev in _parse_feed(blob, source):
            yield ev


def _parse_feed(blob: bytes, source: SourceCfg) -> list[RawEvent]:
    import feedparser  # lazy import keeps cold-start fast

    parsed = feedparser.parse(blob)
    out: list[RawEvent] = []
    now = datetime.now(UTC)
    for entry in getattr(parsed, "entries", []):
        try:
            out.append(_to_raw(entry, source, ingest_ts=now))
        except (KeyError, AttributeError, TypeError, ValueError):
            continue  # skip malformed entries; never crash the loop
    return out


def _to_raw(entry: Any, source: SourceCfg, *, ingest_ts: datetime) -> RawEvent:
    title = str(entry.get("title", "")).strip()
    if not title:
        raise ValueError("entry has no title")
    body = str(entry.get("summary") or entry.get("description") or "").strip()
    url = entry.get("link")
    event_ts = _entry_timestamp(entry, default=ingest_ts)
    return RawEvent(
        source_id=source.id,
        event_ts=event_ts,
        ingest_ts=ingest_ts,
        url=url,
        title=title,
        body=body,
        lang=source.language,
    )


def _entry_timestamp(entry: Any, *, default: datetime) -> datetime:
    raw = entry.get("published") or entry.get("updated")
    if raw is None:
        return default
    try:
        dt: datetime = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return default
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt

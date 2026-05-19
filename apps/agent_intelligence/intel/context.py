"""Per-ticker rolling intel context builder (P2.7).

Returns an ``IntelContextV1`` aggregating the last N hours of events
that name ``ticker`` in their ``target_assets``. Used by the trading
room so persona / quant / fundamental nodes attach context to plans
without re-fetching events from Postgres.

Aggregates are intentionally cheap: sentiment EMA, simple regime score
(stdev of sentiment / floor), per-theme and per-source top-K. The
LLM-driven regime detector lives separately (P7.5).
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Protocol

from schema import IntelContextV1

from .types import Event


class EventQuery(Protocol):
    """How the context builder reaches into the event store. Production
    binds a Postgres-backed implementation; tests can pass a list."""

    async def recent_for_ticker(self, ticker: str, since: datetime) -> list[Event]: ...


class _ListEventQuery:
    """Adapter that satisfies ``EventQuery`` from a plain list of Events."""

    __slots__ = ("_events",)

    def __init__(self, events: list[Event]) -> None:
        self._events = events

    async def recent_for_ticker(self, ticker: str, since: datetime) -> list[Event]:
        return [
            e
            for e in self._events
            if ticker in (e.target_assets or []) and e.event_ts >= since
        ]


def _sentiment_ema(events: list[Event], *, alpha: float = 0.3) -> float:
    if not events:
        return 0.0
    sorted_events = sorted(events, key=lambda e: e.event_ts)
    ema = sorted_events[0].sentiment
    for ev in sorted_events[1:]:
        ema = alpha * ev.sentiment + (1.0 - alpha) * ema
    return max(-1.0, min(1.0, ema))


def _regime_change_score(events: list[Event]) -> float:
    if len(events) < 2:
        return 0.0
    sentiments = [e.sentiment for e in events]
    mean = sum(sentiments) / len(sentiments)
    variance = sum((s - mean) ** 2 for s in sentiments) / len(sentiments)
    std = math.sqrt(variance)
    # Scale to [0, 1]: stdev of 1 (max spread on a [-1, 1] axis) → 1.
    return min(1.0, std)


async def build_context(
    ticker: str,
    *,
    query: EventQuery,
    asof: datetime | None = None,
    window_hours: int = 24,
    top_k: int = 5,
) -> IntelContextV1:
    """Build an ``IntelContextV1`` for ``ticker`` over the last ``window_hours``."""
    asof_ts = asof or datetime.now(UTC)
    since = asof_ts - timedelta(hours=window_hours)
    events = await query.recent_for_ticker(ticker, since)

    themes = Counter()
    sources = Counter()
    notable_ids: list[str] = []
    for ev in events:
        sources[ev.source_id] += 1
        if ev.target_assets:
            for theme in ev.target_assets:
                if theme != ticker:
                    themes[theme] += 1
        if abs(ev.sentiment) > 0.5:
            notable_ids.append(ev.id)

    return IntelContextV1(
        ticker=ticker,
        asof=asof_ts,
        window_hours=window_hours,
        event_count=len(events),
        sentiment_ema=_sentiment_ema(events),
        regime_change_score=_regime_change_score(events),
        top_themes=[t for t, _ in themes.most_common(top_k)],
        top_sources=[s for s, _ in sources.most_common(top_k)],
        notable_event_ids=notable_ids[:top_k],
    )


def from_events(events: list[Event]) -> EventQuery:
    """Convenience helper for tests + the in-memory pipeline path."""
    return _ListEventQuery(events)

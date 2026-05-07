"""Daily coverage selector (workflow 11 §5.5).

Cap: 8 valuations per digest. Tie-breakers:
  1. highest link score
  2. tickers without an active advice in the last 14 days (freshness preference)
  3. alphabetical ticker
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta

from .linker import LinkScore

DEFAULT_DAILY_CAP = 8
FRESHNESS_DAYS = 14


def select(
    scores: Iterable[LinkScore],
    *,
    last_advice_at: Mapping[str, datetime] | None = None,
    asof: datetime | None = None,
    cap: int = DEFAULT_DAILY_CAP,
) -> list[str]:
    last = last_advice_at or {}
    when = asof or datetime.now()
    fresh_cutoff = when - timedelta(days=FRESHNESS_DAYS)

    scored = sorted(scores, key=lambda s: (-s.score, s.ticker))
    seen: set[str] = set()
    fresh: list[str] = []
    stale: list[str] = []
    for s in scored:
        if s.ticker in seen:
            continue
        seen.add(s.ticker)
        last_at = last.get(s.ticker)
        if last_at is None or last_at < fresh_cutoff:
            fresh.append(s.ticker)
        else:
            stale.append(s.ticker)
        if len(fresh) >= cap:
            break

    out = fresh[:cap]
    if len(out) < cap:
        out.extend(stale[: cap - len(out)])
    return out

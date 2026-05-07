"""PIT-correct universe builder (workflow 12 §5.1).

Joins `lake.universe_membership` with the asof predicate. We expose the
predicate as a pure function so tests cover the survivorship-bias case
without a database.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

UniverseId = Literal["SPX", "HSI50", "A50"]


@dataclass(frozen=True, slots=True)
class Membership:
    universe: UniverseId
    ticker: str
    added_at: datetime
    removed_at: datetime | None


def constituents(rows: Iterable[Membership], universe: UniverseId, *, asof: datetime) -> list[str]:
    """Membership active at `asof` for the given universe — PIT correct."""
    out: list[str] = []
    for row in rows:
        if row.universe != universe:
            continue
        if row.added_at > asof:
            continue
        if row.removed_at is not None and row.removed_at <= asof:
            continue
        out.append(row.ticker)
    return sorted(set(out))

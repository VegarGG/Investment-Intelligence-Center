"""Point-in-time correctness helpers (workflow 02 §6 + v2.5 T1.10).

FOUR rules, all enforced here or by the migration:
  1. Every row in lake.timeseries has as_of <= now() at insert.
  2. Backtest reads must filter as_of <= :asof_ts.
  3. Survivorship-corrected universe — historical_universe() joins
     lake.universe_membership with PIT.
  4. v2.5 T1.10: every ingest path provides BOTH `as_of_ts` (when the data
     became knowable to the world) and `ingested_at_ts` (when IIC first saw
     it); `assert_ingest_pit_safe()` enforces this invariant call-site-side
     so a future agent can't silently drop the timestamps and corrupt
     replay determinism.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

import sqlglot
from sqlalchemy.sql import Select
from sqlglot import expressions as exp

from data_lake.exceptions import PITViolation

PIT_TABLES: frozenset[str] = frozenset(
    {
        "timeseries",  # lake.timeseries
        "doc_chunks",  # any join through doc_chunks for backtests
    }
)
"""Tables whose backtest reads must constrain `as_of`."""


def _to_sql(query: str | Select[Any]) -> str:
    if isinstance(query, str):
        return query
    return str(query.compile(compile_kwargs={"literal_binds": False}))


def _references_table(parsed: exp.Expression, table_names: Sequence[str]) -> bool:
    for tbl in parsed.find_all(exp.Table):
        if tbl.name.lower() in {t.lower() for t in table_names}:
            return True
    return False


def _has_as_of_filter(parsed: exp.Expression) -> bool:
    """True if the parsed query has any WHERE/ON clause referencing column
    `as_of` with a comparison operator."""
    for cond in parsed.find_all(exp.Where, exp.Join):
        for col in cond.find_all(exp.Column):
            if col.name.lower() == "as_of":
                # require the column appear inside a comparison, not just a SELECT
                parent = col.parent
                while parent and not isinstance(
                    parent, exp.LT | exp.LTE | exp.GT | exp.GTE | exp.EQ | exp.Between
                ):
                    parent = parent.parent
                if parent is not None:
                    return True
    return False


def assert_pit_safe(query: str | Select[Any], dialect: str = "postgres") -> None:
    """Raise PITViolation if `query` reads from a PIT table without an as_of predicate.

    Examples:
        # OK — predicate present
        assert_pit_safe("SELECT * FROM lake.timeseries WHERE as_of <= '2024-06-01'")

        # FAILS — touches lake.timeseries with no as_of constraint
        assert_pit_safe("SELECT * FROM lake.timeseries WHERE ts <= '2024-06-01'")
    """
    sql = _to_sql(query)
    parsed = cast(exp.Expression, sqlglot.parse_one(sql, read=dialect))
    if not _references_table(parsed, list(PIT_TABLES)):
        return  # query doesn't touch PIT-sensitive tables, nothing to enforce
    if not _has_as_of_filter(parsed):
        raise PITViolation(
            "query touches a PIT table but does not constrain `as_of`. "
            "Backtest reads must include `WHERE as_of <= :asof_ts`."
        )


# ---------------------------------------------------------------------------
# v2.5 T1.10 — ingest-side PIT enforcement.
# ---------------------------------------------------------------------------

INGEST_REQUIRED_FIELDS: tuple[str, str] = ("as_of_ts", "ingested_at_ts")
"""Mandatory PIT timestamp pair on every record entering Postgres / Timescale."""

# Every ingest path that touches PIT-sensitive tables must call
# `assert_ingest_pit_safe(record, source=...)`. Listing each path here makes
# the surface explicit; the test in `tests/chaos/test_pit_replay_determinism.py`
# parametrises over INGEST_PATHS to enforce coverage.
INGEST_PATHS: tuple[str, ...] = (
    "intel.events",
    "fundamental.filings",
    "quant.timeseries",
    "persona.memory",
    # T2 additions (registered now so the test detects when the ingest exists).
    "futu_audit",
    "plan_scorecard",
)


@dataclass(frozen=True, slots=True)
class IngestRecord:
    """Minimal PIT-tagged record. Every ingest path produces this shape."""

    payload: Mapping[str, Any]
    as_of_ts: datetime
    ingested_at_ts: datetime


def assert_ingest_pit_safe(record: Mapping[str, Any], *, source: str) -> None:
    """Reject a record that's missing PIT timestamps or violates monotonicity.

    Plan v2.5 §T1.10: every record entering Postgres / Timescale carries
    ``as_of_ts`` (when the data became knowable) and ``ingested_at_ts``
    (when IIC first saw it). ``as_of_ts <= ingested_at_ts <= now()``.
    """

    missing = [f for f in INGEST_REQUIRED_FIELDS if record.get(f) is None]
    if missing:
        raise PITViolation(
            f"ingest path {source!r} missing PIT timestamps: {missing}"
        )

    as_of = _coerce_dt(record["as_of_ts"], field="as_of_ts", source=source)
    ingested = _coerce_dt(record["ingested_at_ts"], field="ingested_at_ts", source=source)

    if as_of > ingested:
        raise PITViolation(
            f"ingest path {source!r}: as_of_ts={as_of.isoformat()} > "
            f"ingested_at_ts={ingested.isoformat()} — backwards."
        )
    now = datetime.now(UTC)
    if ingested > now:
        raise PITViolation(
            f"ingest path {source!r}: ingested_at_ts={ingested.isoformat()} > "
            f"now={now.isoformat()} — clock skew or future-data injection."
        )


def _coerce_dt(value: Any, *, field: str, source: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise PITViolation(f"{source}.{field} not iso8601: {value!r}") from exc
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise PITViolation(
        f"{source}.{field} must be datetime or iso8601 string, got {type(value).__name__}"
    )


def stamp_ingest(payload: Mapping[str, Any], *, as_of_ts: datetime) -> dict[str, Any]:
    """Return a copy of ``payload`` with PIT timestamps stamped on.

    Convenience for ingest paths that already know `as_of_ts`. We never
    let the caller decide ``ingested_at_ts`` — it's "now()" by definition.
    """
    out = dict(payload)
    out["as_of_ts"] = as_of_ts
    out["ingested_at_ts"] = datetime.now(UTC)
    return out


async def historical_universe(index: str, asof: date) -> list[str]:
    """Return the survivorship-corrected constituents of `index` on `asof`.

    Joins lake.universe_membership with PIT — a name in_to NULL is still active;
    a name with in_to <= asof is excluded.
    """
    from sqlalchemy import text

    from data_lake.postgres import session

    async with session("ro") as s:
        rows = await s.execute(
            text(
                "SELECT ticker FROM lake.universe_membership "
                "WHERE index = :index "
                "  AND in_from <= :asof "
                "  AND (in_to IS NULL OR in_to > :asof) "
                "ORDER BY ticker"
            ),
            {"index": index, "asof": asof},
        )
        return [r[0] for r in rows.all()]

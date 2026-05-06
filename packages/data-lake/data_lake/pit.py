"""Point-in-time correctness helpers (workflow 02 §6).

THREE rules, all enforced here or by the migration:
  1. Every row in lake.timeseries has as_of <= now() at insert.
  2. Backtest reads must filter as_of <= :asof_ts.
  3. Survivorship-corrected universe — historical_universe() joins
     lake.universe_membership with PIT.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

import sqlglot
from sqlglot import expressions as exp
from sqlalchemy.sql import Select

from data_lake.exceptions import PITViolation

PIT_TABLES: frozenset[str] = frozenset({
    "timeseries",  # lake.timeseries
    "doc_chunks",  # any join through doc_chunks for backtests
})
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
                while parent and not isinstance(parent, (exp.LT, exp.LTE, exp.GT, exp.GTE, exp.EQ, exp.Between)):
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
    parsed = sqlglot.parse_one(sql, read=dialect)
    if not _references_table(parsed, list(PIT_TABLES)):
        return  # query doesn't touch PIT-sensitive tables, nothing to enforce
    if not _has_as_of_filter(parsed):
        raise PITViolation(
            "query touches a PIT table but does not constrain `as_of`. "
            "Backtest reads must include `WHERE as_of <= :asof_ts`."
        )


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

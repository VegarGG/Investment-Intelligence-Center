"""Lint: every hypertabled table must include the partitioning column in its PK.

Background: TimescaleDB requires the partitioning column to participate
in every UNIQUE / PRIMARY KEY constraint on a hypertable. Three migrations
in IIC v2.5 originally violated this and only got caught on the linux
fresh-bringup (D6 §1.1 patch #6). This script catches that class of bug
at PR time.

Approach: parse each migration file under
`packages/data-lake/data_lake/migrations/versions/` for:
  - CREATE TABLE statements (capture the PRIMARY KEY columns)
  - SELECT create_hypertable('schema.table', '<partitioning_col>', …)

Then for each (table, partitioning_col) pair, verify the table's PK
contains the partitioning column.

Exit status: 0 = clean; 1 = found violations.

P1.5 acceptance criterion: "CI passes today; CI fails on a deliberately
re-broken regression PR."
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MIGRATIONS = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "data-lake"
    / "data_lake"
    / "migrations"
    / "versions"
)

CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+([a-zA-Z_][\w\.]*)\s*\((.+?)\);",
    re.IGNORECASE | re.DOTALL,
)
PK_INLINE = re.compile(r"PRIMARY\s+KEY\s*\(([^)]+)\)", re.IGNORECASE)
PK_COL_DECL = re.compile(r"^\s*([a-zA-Z_]\w*)\s+[\w\s\(\)]+PRIMARY\s+KEY", re.IGNORECASE)
HYPERTABLE = re.compile(
    r"create_hypertable\s*\(\s*'([\w\.]+)'\s*,\s*'(\w+)'",
    re.IGNORECASE,
)


def _parse_pk_columns(table_body: str) -> set[str]:
    """Return the lowercase PK column names declared inside a table body."""
    m = PK_INLINE.search(table_body)
    if m:
        return {c.strip().lower() for c in m.group(1).split(",")}
    cols: set[str] = set()
    for line in table_body.splitlines():
        m = PK_COL_DECL.match(line)
        if m:
            cols.add(m.group(1).lower())
    return cols


def check(path: Path) -> list[str]:
    """Return a list of violation strings for one migration file."""
    text = path.read_text()
    tables: dict[str, set[str]] = {}
    for tbl, body in CREATE_TABLE.findall(text):
        tables[tbl.lower()] = _parse_pk_columns(body)

    violations: list[str] = []
    for tbl, partcol in HYPERTABLE.findall(text):
        pk = tables.get(tbl.lower())
        if pk is None:
            # CREATE TABLE may live in a previous migration; can't verify here.
            continue
        if partcol.lower() not in pk:
            violations.append(
                f"{path.name}: hypertable {tbl!r} partitioned on "
                f"{partcol!r} but PK is {sorted(pk)!r} — must include the "
                f"partitioning column."
            )
    return violations


def main() -> int:
    if not MIGRATIONS.exists():
        print(f"missing migrations dir: {MIGRATIONS}", file=sys.stderr)
        return 1
    failures: list[str] = []
    for p in sorted(MIGRATIONS.glob("*.py")):
        failures.extend(check(p))
    if failures:
        print("alembic hypertable PK violations:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("alembic hypertable PK lint: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

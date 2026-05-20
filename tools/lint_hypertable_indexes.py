"""Lint: forbid hand-created indexes that duplicate Timescale's auto-index.

D7.1 §H2.4 — TimescaleDB's ``create_hypertable(table, time_col)`` already
creates a B-tree index named exactly ``<table>_<time_col>_idx`` on the
time column. A migration that subsequently runs ``op.create_index(
"<table>_<time_col>_idx", ...)`` raises ``relation already exists`` the
moment a fresh DB tries to upgrade through it — and only on the *first*
deploy. We dodged this on 0007 (see fix commit 25f26ae); this lint
prevents the next instance.

Approach
--------
Parse each Alembic migration under
``packages/data-lake/data_lake/migrations/versions/`` for:

* ``create_hypertable("lake.<table>", "<time_col>", ...)`` calls; capture
  the implicit auto-index name ``<table>_<time_col>_idx``.
* ``op.create_index(...)`` calls whose first argument equals one of the
  captured auto-index names.

Twin of :mod:`tools.lint_hypertable_pk`.

Exit status: 0 = clean; 1 = violations found.
"""

from __future__ import annotations

import pathlib
import re
import sys

MIGRATIONS = pathlib.Path("packages/data-lake/data_lake/migrations/versions")

# Match: create_hypertable('lake.<table>', '<time_col>', ...) or
# create_hypertable("lake.<table>", "<time_col>", ...). The schema prefix
# is optional so a future migration that drops the lake.* convention is
# still caught.
HYPERTABLE_RE = re.compile(
    r"""create_hypertable\(\s*
        ['"](?:\w+\.)?(?P<table>\w+)['"]\s*,\s*
        ['"](?P<time_col>\w+)['"]
    """,
    re.VERBOSE,
)

# Match: op.create_index("<name>", ...) or create_index("<name>", ...).
CREATE_INDEX_RE = re.compile(
    r"""(?:op\.)?create_index\(\s*['"](?P<index>\w+)['"]"""
)


def lint_file(path: pathlib.Path) -> list[str]:
    src = path.read_text(encoding="utf-8")

    auto_index_names: set[str] = set()
    for m in HYPERTABLE_RE.finditer(src):
        auto_index_names.add(f"{m.group('table')}_{m.group('time_col')}_idx")

    if not auto_index_names:
        return []

    errors: list[str] = []
    for m in CREATE_INDEX_RE.finditer(src):
        index_name = m.group("index")
        if index_name in auto_index_names:
            errors.append(
                f"{path.name}: redundant index '{index_name}' — "
                f"create_hypertable already creates it."
            )
    return errors


def main() -> int:
    if not MIGRATIONS.exists():
        print(f"::warning::migrations dir not found: {MIGRATIONS}")
        return 0

    all_errors: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.py")):
        all_errors.extend(lint_file(path))

    if all_errors:
        for err in all_errors:
            print(f"::error::{err}", file=sys.stderr)
        return 1

    print("OK: no redundant hypertable time-column indexes found")
    return 0


if __name__ == "__main__":
    sys.exit(main())

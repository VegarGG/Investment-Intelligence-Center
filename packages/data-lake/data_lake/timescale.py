"""TimescaleDB hypertable helpers (workflow 02 §5.2, §5.5).

Migrations create the hypertables; these helpers exist for ad-hoc admin work
and for tests that need to assert the hypertable shape.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def is_hypertable(conn: AsyncConnection, table: str, schema: str = "lake") -> bool:
    """True iff `schema.table` is registered as a Timescale hypertable."""
    row = await conn.execute(
        text(
            "SELECT 1 FROM timescaledb_information.hypertables "
            "WHERE hypertable_schema = :schema AND hypertable_name = :table"
        ),
        {"schema": schema, "table": table},
    )
    return row.first() is not None


async def hypertable_chunk_count(conn: AsyncConnection, table: str, schema: str = "lake") -> int:
    row = await conn.execute(
        text(
            "SELECT count(*) FROM timescaledb_information.chunks "
            "WHERE hypertable_schema = :schema AND hypertable_name = :table"
        ),
        {"schema": schema, "table": table},
    )
    n = row.scalar_one()
    return int(n)

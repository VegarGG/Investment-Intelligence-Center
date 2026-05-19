"""lake.secretary_thread — conversation memory for the secretary (P6.5).

Bounded by retention: rolling 30 days, 100 turns per thread (enforced
client-side; this migration only owns the storage).

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.secretary_thread (
          thread_id   UUID NOT NULL,
          ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
          role        TEXT NOT NULL CHECK (role IN ('user','assistant','system','tool')),
          content     TEXT NOT NULL,
          trace_id    TEXT,
          -- TimescaleDB hypertable PK rule.
          PRIMARY KEY (thread_id, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.secretary_thread', 'ts', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )
    op.execute("CREATE INDEX secretary_thread_id_ts_idx ON lake.secretary_thread (thread_id, ts DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.secretary_thread CASCADE")

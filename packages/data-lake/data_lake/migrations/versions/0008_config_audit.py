"""lake.config_audit hash-chained edit log (P3.2).

Every config write performed via the admin API appends one row. The chain
hash semantics mirror lake.advice (migration 0002) so a mutation of any
row breaks the verify pass.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.config_audit (
          id              UUID NOT NULL,
          ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
          actor           TEXT NOT NULL,
          path            TEXT NOT NULL,
          before_hash     BYTEA,
          after_hash      BYTEA NOT NULL,
          prev_chain_hash BYTEA,
          chain_hash      BYTEA NOT NULL,
          reason          TEXT,
          -- TimescaleDB requires the partitioning column in the PK.
          PRIMARY KEY (id, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.config_audit', 'ts', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )
    op.execute("CREATE INDEX config_audit_path_ts_idx ON lake.config_audit (path, ts DESC)")
    op.execute("CREATE INDEX config_audit_actor_ts_idx ON lake.config_audit (actor, ts DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.config_audit CASCADE")

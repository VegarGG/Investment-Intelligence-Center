"""Eval drift hypertable (workflow 30 §4).

Stores one row per weekly drift run per caller. The `iic-006-eval`
Grafana dashboard reads from this table; `PROMPT_EVAL_REGRESSION` fires
when `regression_flag` flips to true.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.eval_runs (
          id               UUID NOT NULL,
          ts               TIMESTAMPTZ NOT NULL DEFAULT now(),
          caller_id        TEXT NOT NULL,
          prompt_version   TEXT NOT NULL,
          judge_version    TEXT NOT NULL,
          mean_score       DOUBLE PRECISION NOT NULL,
          per_prompt       JSONB NOT NULL,
          baseline_score   DOUBLE PRECISION,
          regression_flag  BOOLEAN NOT NULL DEFAULT false,
          -- TimescaleDB requires the partitioning column (ts) to be part
          -- of any UNIQUE/PRIMARY KEY constraint.
          PRIMARY KEY (id, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.eval_runs', 'ts',"
        " chunk_time_interval => INTERVAL '30 days');"
    )
    op.execute("CREATE INDEX eval_runs_caller_ts_idx ON lake.eval_runs (caller_id, ts DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.eval_runs CASCADE;")

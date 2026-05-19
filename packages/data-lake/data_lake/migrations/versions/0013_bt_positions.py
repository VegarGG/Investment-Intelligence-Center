"""lake.bt_positions — virtual portfolio book for the backtester (P7.7).

One row per published advice. ``opened_at`` is the partitioning column
(hypertable PK rule). ``state`` walks open → closed; ``pnl`` is updated
on each mark-to-market cycle.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.bt_positions (
          advice_id   TEXT NOT NULL,
          opened_at   TIMESTAMPTZ NOT NULL,
          ticker      TEXT NOT NULL,
          direction   TEXT NOT NULL CHECK (direction IN ('long','short')),
          entry_price DOUBLE PRECISION NOT NULL,
          target      DOUBLE PRECISION,
          stop        DOUBLE PRECISION,
          horizon_days INT,
          state       TEXT NOT NULL DEFAULT 'open'
                          CHECK (state IN ('open','closed_target','closed_stop','closed_horizon','closed_other')),
          fills       JSONB NOT NULL DEFAULT '[]'::jsonb,
          pnl_usd     DOUBLE PRECISION NOT NULL DEFAULT 0,
          closed_at   TIMESTAMPTZ,
          source_agent TEXT,
          PRIMARY KEY (advice_id, opened_at)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.bt_positions', 'opened_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )
    op.execute("CREATE INDEX bt_positions_ticker_idx ON lake.bt_positions (ticker, opened_at DESC)")
    op.execute("CREATE INDEX bt_positions_state_idx ON lake.bt_positions (state, opened_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.bt_positions CASCADE")

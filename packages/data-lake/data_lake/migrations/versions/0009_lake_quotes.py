"""lake.quotes hypertable for live + historical quote ticks (P4.4).

Producers:
  - FutuQuoteClient    src='futu'
  - ccxt crypto writer src='binance' (and friends)
  - FX writer          src='fred' / 'oanda'

Consumers:
  - agent_quant /run/factors  (momentum, mean reversion, vol risk premium)
  - agent_fundamental         (current-price lookup for valuation)
  - agent_backtest book       (mark-to-market every quote cycle)

The PK is composite ``(ticker, ts)`` to satisfy TimescaleDB's hypertable
PK rule. Monthly chunks; recent month stays hot.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.quotes (
          ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
          ticker    TEXT NOT NULL,
          exch      TEXT NOT NULL,
          bid       DOUBLE PRECISION,
          ask       DOUBLE PRECISION,
          last      DOUBLE PRECISION NOT NULL,
          vol       BIGINT,
          src       TEXT NOT NULL,
          PRIMARY KEY (ticker, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.quotes', 'ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )
    op.execute("CREATE INDEX quotes_src_ts_idx ON lake.quotes (src, ts DESC)")
    op.execute("CREATE INDEX quotes_exch_ts_idx ON lake.quotes (exch, ts DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.quotes CASCADE")

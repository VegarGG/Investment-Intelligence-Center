"""LLM telemetry tables (workflow 03 §11, §7).

Creates the three tables `packages/llm-client` writes to:
  - lake.llm_calls            hypertable, one row per chat()/embed() call
  - lake.llm_spend_daily      rolling 30-day spend, primary cost-meter source
  - lake.llm_pricing_history  audit trail of every pricing-table change

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- lake.llm_calls (hypertable) -------------------------------------
    op.execute(
        """
        CREATE TABLE lake.llm_calls (
          id              UUID NOT NULL,
          ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
          caller_id       TEXT NOT NULL,
          tier            TEXT NOT NULL CHECK (tier IN ('flash','pro','embed')),
          model           TEXT NOT NULL,
          prompt_tokens   INT NOT NULL,
          completion_tokens INT NOT NULL,
          cost_usd        DOUBLE PRECISION NOT NULL,
          latency_ms      INT NOT NULL,
          cached          BOOLEAN NOT NULL,
          fallback_used   BOOLEAN NOT NULL,
          outcome         TEXT NOT NULL CHECK (outcome IN ('ok','error','timeout','rate_limit')),
          error           TEXT,
          request_hash    BYTEA,
          response_hash   BYTEA,
          -- TimescaleDB requires the partitioning column (ts) to participate
          -- in any UNIQUE/PRIMARY KEY constraint, so use a composite PK.
          PRIMARY KEY (id, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.llm_calls', 'ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )
    op.execute("CREATE INDEX llm_calls_caller_ts_idx ON lake.llm_calls (caller_id, ts DESC)")
    op.execute("CREATE INDEX llm_calls_tier_ts_idx ON lake.llm_calls (tier, ts DESC)")

    # ---- lake.llm_spend_daily (cost-meter source of truth) ---------------
    op.execute(
        """
        CREATE TABLE lake.llm_spend_daily (
          date           DATE NOT NULL,
          tier           TEXT NOT NULL CHECK (tier IN ('flash','pro','embed')),
          fallback_used  BOOLEAN NOT NULL DEFAULT false,
          cost_usd       DOUBLE PRECISION NOT NULL DEFAULT 0,
          calls          INT NOT NULL DEFAULT 0,
          PRIMARY KEY (date, tier, fallback_used)
        );
        """
    )

    # ---- lake.llm_pricing_history (audit log for pricing.PRICING) --------
    op.execute(
        """
        CREATE TABLE lake.llm_pricing_history (
          id            BIGSERIAL PRIMARY KEY,
          ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
          model         TEXT NOT NULL,
          in_per_1m_usd DOUBLE PRECISION NOT NULL,
          out_per_1m_usd DOUBLE PRECISION NOT NULL,
          source        TEXT NOT NULL,
          notes         TEXT
        );
        """
    )
    op.execute(
        "CREATE INDEX llm_pricing_history_model_ts_idx "
        "ON lake.llm_pricing_history (model, ts DESC)"
    )

    # ---- role grants -----------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_app') THEN
            EXECUTE 'GRANT INSERT ON lake.llm_calls TO iic_app';
            EXECUTE 'GRANT SELECT, INSERT, UPDATE ON lake.llm_spend_daily TO iic_app';
            EXECUTE 'GRANT SELECT, INSERT ON lake.llm_pricing_history TO iic_app';
            EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE lake.llm_pricing_history_id_seq TO iic_app';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_ro') THEN
            EXECUTE 'GRANT SELECT ON lake.llm_calls, lake.llm_spend_daily, '
                    'lake.llm_pricing_history TO iic_ro';
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.llm_pricing_history")
    op.execute("DROP TABLE IF EXISTS lake.llm_spend_daily")
    op.execute("DROP TABLE IF EXISTS lake.llm_calls")

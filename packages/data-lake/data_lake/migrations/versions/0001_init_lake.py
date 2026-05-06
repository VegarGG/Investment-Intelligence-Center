"""init lake schema (workflow 02 §5).

Creates the `lake` schema, every base table, the Timescale hypertables, and
the GRANT/REVOKE matrix for the three roles. Roles themselves are created
out-of-band by infra/postgres/init-roles.sql.

Revision ID: 0001
Revises:
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- extensions -------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("CREATE SCHEMA IF NOT EXISTS lake")
    op.execute("CREATE SCHEMA IF NOT EXISTS partman")

    # ---- lake.events (PARTITIONED, monthly, via pg_partman) ---------------
    op.execute(
        """
        CREATE TABLE lake.events (
          id            BIGSERIAL,
          source_id     TEXT      NOT NULL,
          source_lean   TEXT,
          source_region TEXT,
          event_ts      TIMESTAMPTZ NOT NULL,
          ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
          url           TEXT,
          title         TEXT,
          body          TEXT,
          lang          TEXT,
          raw           JSONB     NOT NULL,
          hash          BYTEA     NOT NULL,
          PRIMARY KEY (id, event_ts),
          UNIQUE (hash, event_ts)
        ) PARTITION BY RANGE (event_ts);
        """
    )
    op.execute("CREATE INDEX events_event_ts_idx ON lake.events (event_ts DESC)")
    op.execute("CREATE INDEX events_source_idx ON lake.events (source_id, event_ts DESC)")
    op.execute("CREATE INDEX events_raw_gin ON lake.events USING gin (raw jsonb_path_ops)")
    op.execute(
        """
        SELECT partman.create_parent(
          p_parent_table := 'lake.events',
          p_control      := 'event_ts',
          p_type         := 'native',
          p_interval     := '1 month',
          p_premake      := 4
        );
        """
    )
    op.execute(
        """
        UPDATE partman.part_config
           SET retention            = '365 days',
               retention_keep_table = false
         WHERE parent_table = 'lake.events';
        """
    )

    # ---- lake.timeseries (Timescale hypertable, OHLCV + factors) ----------
    op.execute(
        """
        CREATE TABLE lake.timeseries (
          symbol  TEXT NOT NULL,
          ts      TIMESTAMPTZ NOT NULL,
          open    DOUBLE PRECISION,
          high    DOUBLE PRECISION,
          low     DOUBLE PRECISION,
          close   DOUBLE PRECISION,
          volume  DOUBLE PRECISION,
          source  TEXT NOT NULL,
          as_of   TIMESTAMPTZ NOT NULL,
          PRIMARY KEY (symbol, ts, source)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.timeseries', 'ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )
    op.execute("SELECT add_retention_policy('lake.timeseries', INTERVAL '10 years');")
    op.execute("CREATE INDEX timeseries_symbol_ts_idx ON lake.timeseries (symbol, ts DESC);")
    # PIT-rule guard: as_of must never be in the future at insert time.
    op.execute(
        """
        ALTER TABLE lake.timeseries
          ADD CONSTRAINT timeseries_as_of_not_future
          CHECK (as_of <= now() + INTERVAL '1 minute');
        """
    )

    # ---- lake.docs + lake.doc_chunks (filings + chunked text) -------------
    op.execute(
        """
        CREATE TABLE lake.docs (
          doc_id     UUID        PRIMARY KEY,
          kind       TEXT        NOT NULL,
          ticker     TEXT,
          filed_at   TIMESTAMPTZ NOT NULL,
          source_url TEXT,
          raw_path   TEXT,
          parsed     BOOLEAN     NOT NULL DEFAULT false,
          parse_err  TEXT
        );
        """
    )
    op.execute("CREATE INDEX docs_ticker_filed_idx ON lake.docs (ticker, filed_at DESC);")
    op.execute(
        """
        CREATE TABLE lake.doc_chunks (
          chunk_id     UUID        PRIMARY KEY,
          doc_id       UUID        REFERENCES lake.docs(doc_id) ON DELETE CASCADE,
          chunk_idx    INT         NOT NULL,
          text         TEXT        NOT NULL,
          token_count  INT,
          embedding_id TEXT
        );
        """
    )

    # ---- lake.advice (the immutable ledger) -------------------------------
    op.execute(
        """
        CREATE TABLE lake.advice (
          id              TEXT PRIMARY KEY,
          schema          TEXT NOT NULL,
          agent           TEXT NOT NULL,
          issued_at       TIMESTAMPTZ NOT NULL,
          asset_kind      TEXT NOT NULL,
          asset_ticker    TEXT NOT NULL,
          asset_venue     TEXT,
          asset_name      TEXT,
          thesis          TEXT NOT NULL,
          direction       TEXT NOT NULL CHECK (direction IN ('long','short','flat')),
          confidence      DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
          entry_low       DOUBLE PRECISION NOT NULL,
          entry_high      DOUBLE PRECISION NOT NULL,
          target_low      DOUBLE PRECISION NOT NULL,
          target_high     DOUBLE PRECISION NOT NULL,
          stop_loss       DOUBLE PRECISION NOT NULL,
          horizon_days    INT NOT NULL,
          max_drawdown_pct DOUBLE PRECISION NOT NULL,
          sizing_hint_pct_nav DOUBLE PRECISION,
          expires_at      TIMESTAMPTZ NOT NULL,
          evidence        JSONB NOT NULL,
          payload         JSONB NOT NULL,
          payload_canonical BYTEA NOT NULL,
          prev_hash       BYTEA,
          row_hash        BYTEA NOT NULL,
          CONSTRAINT advice_id_format CHECK (id ~ '^[0-9A-HJKMNP-TV-Z]{26}$')
        );
        """
    )
    op.execute("CREATE UNIQUE INDEX advice_agent_chain_idx ON lake.advice (agent, issued_at, id)")
    op.execute("CREATE INDEX advice_ticker_idx ON lake.advice (asset_ticker, issued_at DESC)")
    # Concurrency guard: two writers cannot share the same prev_hash for one agent.
    op.execute(
        "CREATE UNIQUE INDEX advice_agent_prev_hash_idx ON lake.advice (agent, prev_hash) "
        "WHERE prev_hash IS NOT NULL"
    )
    # The chain-head row (prev_hash IS NULL) — one per agent.
    op.execute(
        "CREATE UNIQUE INDEX advice_agent_chain_head_idx ON lake.advice (agent) "
        "WHERE prev_hash IS NULL"
    )

    # ---- lake.backtest_* --------------------------------------------------
    op.execute(
        """
        CREATE TABLE lake.backtest_positions (
          id           BIGSERIAL PRIMARY KEY,
          advice_id    TEXT NOT NULL REFERENCES lake.advice(id),
          agent        TEXT NOT NULL,
          ticker       TEXT NOT NULL,
          opened_at    TIMESTAMPTZ NOT NULL,
          entry_px     DOUBLE PRECISION NOT NULL,
          size_usd     DOUBLE PRECISION NOT NULL,
          stop_loss    DOUBLE PRECISION NOT NULL,
          target_low   DOUBLE PRECISION NOT NULL,
          target_high  DOUBLE PRECISION NOT NULL,
          state        TEXT NOT NULL CHECK (state IN ('open','closed')),
          closed_at    TIMESTAMPTZ,
          exit_px      DOUBLE PRECISION,
          exit_reason  TEXT,
          pnl_usd      DOUBLE PRECISION,
          pnl_r        DOUBLE PRECISION,
          max_dd_pct   DOUBLE PRECISION
        );
        """
    )
    op.execute(
        "CREATE INDEX backtest_positions_agent_state_idx "
        "ON lake.backtest_positions (agent, state)"
    )
    op.execute(
        """
        CREATE TABLE lake.backtest_marks (
          position_id BIGINT NOT NULL REFERENCES lake.backtest_positions(id) ON DELETE CASCADE,
          ts          TIMESTAMPTZ NOT NULL,
          mark_px     DOUBLE PRECISION NOT NULL,
          pnl_usd     DOUBLE PRECISION NOT NULL,
          PRIMARY KEY (position_id, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.backtest_marks', 'ts', "
        "chunk_time_interval => INTERVAL '14 days', if_not_exists => TRUE);"
    )
    op.execute(
        """
        CREATE TABLE lake.backtest_attribution_daily (
          agent     TEXT NOT NULL,
          date      DATE NOT NULL,
          trades    INT  NOT NULL,
          pnl_usd   DOUBLE PRECISION NOT NULL,
          hit_rate  DOUBLE PRECISION,
          r_avg     DOUBLE PRECISION,
          sharpe    DOUBLE PRECISION,
          max_dd    DOUBLE PRECISION,
          notes     TEXT,
          PRIMARY KEY (agent, date)
        );
        """
    )

    # ---- reference data (workflow 02 §7.3) --------------------------------
    op.execute(
        """
        CREATE TABLE lake.universe_membership (
          index    TEXT NOT NULL,
          ticker   TEXT NOT NULL,
          in_from  DATE NOT NULL,
          in_to    DATE,
          PRIMARY KEY (index, ticker, in_from)
        );
        """
    )
    op.execute(
        "CREATE INDEX universe_membership_index_idx "
        "ON lake.universe_membership (index, in_from, in_to)"
    )
    op.execute(
        """
        CREATE TABLE lake.calendar_events (
          ticker  TEXT NOT NULL,
          kind    TEXT NOT NULL,
          ts      TIMESTAMPTZ NOT NULL,
          PRIMARY KEY (ticker, kind, ts)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE lake.macro_releases (
          series_id      TEXT PRIMARY KEY,
          schedule_cron  TEXT NOT NULL
        );
        """
    )

    # ---- role grants (roles created by infra/postgres/init-roles.sql) -----
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_app') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA lake TO iic_app';
            EXECUTE 'GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA lake TO iic_app';
            EXECUTE 'GRANT UPDATE, DELETE ON lake.docs, lake.doc_chunks, lake.calendar_events, '
                    'lake.macro_releases, lake.universe_membership, lake.backtest_positions, '
                    'lake.backtest_marks, lake.backtest_attribution_daily TO iic_app';
            EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lake TO iic_app';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_ro') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA lake TO iic_ro';
            EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA lake TO iic_ro';
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS lake CASCADE")

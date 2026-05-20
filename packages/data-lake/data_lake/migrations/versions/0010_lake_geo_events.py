"""lake.geo_events for the geo dashboard (P5.1).

Append-only stream of geocoded events sourced from GDELT 2.0 GKG (and
later, other geo feeds). The map dashboard reads from this hypertable.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.geo_events (
          event_id   UUID NOT NULL DEFAULT gen_random_uuid(),
          ts         TIMESTAMPTZ NOT NULL,
          lat        DOUBLE PRECISION,
          lon        DOUBLE PRECISION,
          theme      TEXT,
          tone       DOUBLE PRECISION,
          src_url    TEXT,
          urls       TEXT[],
          place      TEXT,
          gkg_id     TEXT,
          PRIMARY KEY (event_id, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.geo_events', 'ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )
    # `create_hypertable` already creates `geo_events_ts_idx` on the time
    # dimension; don't redeclare it.
    op.execute("CREATE INDEX geo_events_theme_idx ON lake.geo_events (theme, ts DESC)")
    op.execute(
        "CREATE INDEX geo_events_latlon_idx ON lake.geo_events (lat, lon)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.geo_events CASCADE")

"""pgvector extension + lake.intel_embeds (P2.3).

Stores per-event embedding vectors for the semantic dedupe gate.

Acceptance criterion: integration test inserts 100 events; semantically-
near-duplicate rejection rate ≥ 80% on a labelled mini-corpus.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")  # gen_random_uuid()
    op.execute(
        """
        CREATE TABLE lake.intel_embeds (
          event_id  UUID NOT NULL,
          embedding VECTOR(1536) NOT NULL,
          ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (event_id, ts)
        );
        """
    )
    op.execute(
        "SELECT create_hypertable('lake.intel_embeds', 'ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )
    # Cosine similarity uses the `<=>` op; an IVF index keeps recall while
    # bounding latency on large corpora.
    op.execute(
        "CREATE INDEX intel_embeds_cos_idx ON lake.intel_embeds "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )
    # D7.1 §H2.7 — do NOT create intel_embeds_ts_idx here. create_hypertable()
    # above already created a B-tree index on the time column with exactly
    # that name; re-creating raises 'relation already exists' on fresh DB.


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.intel_embeds CASCADE;")
    # Do NOT drop the vector extension — other tables may depend on it.

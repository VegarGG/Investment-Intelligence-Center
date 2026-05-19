"""lake.user_prefs — secretary's per-user preference store (P6.4).

Tracks the runtime state slash commands mutate: tone, mute, push
frequency, persona watchlist priorities. Tiny by design — never expected
to exceed thousands of rows.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.user_prefs (
          user_id      TEXT NOT NULL,
          key          TEXT NOT NULL,
          value        TEXT NOT NULL,
          expires_at   TIMESTAMPTZ,
          updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (user_id, key)
        );
        """
    )
    op.execute("CREATE INDEX user_prefs_updated_idx ON lake.user_prefs (updated_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lake.user_prefs CASCADE")

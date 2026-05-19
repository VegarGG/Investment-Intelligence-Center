"""Allow ``outcome='skipped'`` on lake.llm_calls (P0.6).

Migration 0003 created lake.llm_calls with
``CHECK (outcome IN ('ok','error','timeout','rate_limit'))``. Phase P0.6
extends the audit log to also record synthetic-skip returns, which use
``outcome='skipped'``. Update the CHECK to include the new value.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE lake.llm_calls DROP CONSTRAINT IF EXISTS llm_calls_outcome_check")
    op.execute(
        "ALTER TABLE lake.llm_calls ADD CONSTRAINT llm_calls_outcome_check "
        "CHECK (outcome IN ('ok','error','timeout','rate_limit','skipped'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE lake.llm_calls DROP CONSTRAINT IF EXISTS llm_calls_outcome_check")
    op.execute(
        "ALTER TABLE lake.llm_calls ADD CONSTRAINT llm_calls_outcome_check "
        "CHECK (outcome IN ('ok','error','timeout','rate_limit'))"
    )

"""advice ledger trigger + UPDATE/DELETE revoke (workflow 02 §5.4).

Defense in depth on top of the Python writer:
  - INSERT trigger enforces chain linkage: every non-head row's prev_hash
    must equal an existing row's row_hash for the same agent. (The unique
    indexes from 0001 already guarantee one chain head per agent and no two
    rows sharing a prev_hash; the trigger closes the remaining gap by
    rejecting fabricated prev_hash values.)
  - UPDATE and DELETE on lake.advice are revoked from iic_app — the row is
    immutable from the application's POV.

Tamper detection (recomputing sha256 of prev_hash || canonical payload) is
done Python-side in `data_lake.advice_ledger.verify_chain`, since Postgres'
JSONB text serialization is not byte-identical to orjson's canonical output.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op  # type: ignore[import]

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION lake.advice_chain_check()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
          -- chain head (prev_hash NULL) is always allowed — uniqueness enforced
          -- by the partial index advice_agent_chain_head_idx.
          IF NEW.prev_hash IS NULL THEN
            RETURN NEW;
          END IF;

          -- Non-head rows must point at an existing row for the same agent.
          IF NOT EXISTS (
            SELECT 1 FROM lake.advice
             WHERE agent = NEW.agent
               AND row_hash = NEW.prev_hash
          ) THEN
            RAISE EXCEPTION
              'advice chain linkage failed for id=% agent=%: prev_hash references no existing row',
              NEW.id, NEW.agent
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;

          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER advice_chain_check_trigger
        BEFORE INSERT ON lake.advice
        FOR EACH ROW EXECUTE FUNCTION lake.advice_chain_check();
        """
    )

    # Application role has only INSERT — no UPDATE, no DELETE on the ledger.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_app') THEN
            EXECUTE 'REVOKE UPDATE, DELETE ON lake.advice FROM iic_app';
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS advice_chain_check_trigger ON lake.advice")
    op.execute("DROP FUNCTION IF EXISTS lake.advice_chain_check()")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_app') THEN
            EXECUTE 'GRANT UPDATE, DELETE ON lake.advice TO iic_app';
          END IF;
        END
        $$;
        """
    )

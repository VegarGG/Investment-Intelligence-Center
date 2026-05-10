"""lake.futu_audit ledger + chain trigger + UPDATE/DELETE revoke (v2.5 N3.0).

Mirrors lake.advice (migration 0002):
  - Append-only, hash-chained per futu_id_hash.
  - BEFORE INSERT trigger enforces chain linkage (non-head rows must point
    at an existing row's entry_hash for the same futu_id_hash).
  - UPDATE and DELETE on lake.futu_audit are revoked from iic_app — the
    row is immutable from the application's POV.

Hash recompute is done Python-side in
``apps.agent_futu.futu.audit:PgFutuAuditLog.verify_chain``. The trigger
guards against fabricated prev_hash linkage; the Python verifier guards
against mutated payload columns.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lake.futu_audit (
          id            BIGSERIAL PRIMARY KEY,
          entry_id      TEXT        NOT NULL UNIQUE,
          futu_id_hash  TEXT        NOT NULL,
          method        TEXT        NOT NULL,
          args_repr     TEXT,
          kwargs_repr   TEXT,
          issued_at     TIMESTAMPTZ NOT NULL,
          prev_hash     TEXT        NOT NULL,
          entry_hash    TEXT        NOT NULL UNIQUE,
          status        TEXT        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','ok','error')),
          summary       TEXT,
          error         TEXT
        );
        """
    )
    op.execute(
        "CREATE INDEX futu_audit_fid_issued_idx "
        "ON lake.futu_audit (futu_id_hash, issued_at DESC, id DESC)"
    )
    # Per-futu_id_hash chain head: zero-prev (the all-zero sentinel) is the
    # only allowed head, and it appears at most once per futu_id_hash.
    op.execute(
        "CREATE UNIQUE INDEX futu_audit_chain_head_idx "
        "ON lake.futu_audit (futu_id_hash) "
        "WHERE prev_hash = '" + ("0" * 64) + "'"
    )
    # Concurrency guard: two writers cannot share the same prev_hash for
    # the same futu_id_hash.
    op.execute(
        "CREATE UNIQUE INDEX futu_audit_fid_prev_hash_idx "
        "ON lake.futu_audit (futu_id_hash, prev_hash)"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION lake.futu_audit_chain_check()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
          -- Chain head: prev_hash is the all-zero sentinel. Always allowed;
          -- uniqueness is enforced by futu_audit_chain_head_idx.
          IF NEW.prev_hash = repeat('0', 64) THEN
            RETURN NEW;
          END IF;

          -- Non-head rows must point at an existing row's entry_hash for
          -- the same futu_id_hash.
          IF NOT EXISTS (
            SELECT 1 FROM lake.futu_audit
             WHERE futu_id_hash = NEW.futu_id_hash
               AND entry_hash   = NEW.prev_hash
          ) THEN
            RAISE EXCEPTION
              'futu_audit chain linkage failed for entry_id=% futu_id_hash=%: '
              'prev_hash references no existing row',
              NEW.entry_id, NEW.futu_id_hash
              USING ERRCODE = 'integrity_constraint_violation';
          END IF;

          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER futu_audit_chain_check_trigger
        BEFORE INSERT ON lake.futu_audit
        FOR EACH ROW EXECUTE FUNCTION lake.futu_audit_chain_check();
        """
    )

    # Application role: INSERT only; no UPDATE, no DELETE on the audit ledger.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_app') THEN
            EXECUTE 'GRANT INSERT, SELECT ON lake.futu_audit TO iic_app';
            EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE lake.futu_audit_id_seq TO iic_app';
            -- Defense in depth: explicitly revoke even though the GRANT
            -- above doesn't include UPDATE/DELETE — guards against later
            -- migrations that re-grant ALL.
            EXECUTE 'REVOKE UPDATE, DELETE ON lake.futu_audit FROM iic_app';
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_ro') THEN
            EXECUTE 'GRANT SELECT ON lake.futu_audit TO iic_ro';
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS futu_audit_chain_check_trigger ON lake.futu_audit")
    op.execute("DROP FUNCTION IF EXISTS lake.futu_audit_chain_check()")
    op.execute("DROP TABLE IF EXISTS lake.futu_audit")

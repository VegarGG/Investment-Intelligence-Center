-- IIC v2.1 — Postgres roles bootstrap (workflow 02 §7.1).
--
-- Idempotent role provisioning. Run once per cluster as a superuser before
-- the first `alembic upgrade head`. Subsequent migration GRANTs/REVOKEs
-- assume these three roles exist.
--
--   psql -U postgres -d iic -f infra/postgres/init-roles.sql
--
-- Passwords come from .env (POSTGRES_PASSWORD, POSTGRES_PASSWORD_RO,
-- POSTGRES_PASSWORD_MIGRATION). Set them via psql variables, e.g.:
--
--   psql -v app_pw="'…'" -v ro_pw="'…'" -v mig_pw="'…'" -f init-roles.sql

\set ON_ERROR_STOP on

-- psql's :'var' substitution does NOT expand inside dollar-quoted blocks
-- (DO $$ ... $$). Stash the passwords in session-scoped custom GUCs at the
-- top-level (where psql substitution does work) and read them back from
-- inside the DO block via current_setting().
SELECT set_config('iic.app_pw', :'app_pw', false);
SELECT set_config('iic.ro_pw',  :'ro_pw',  false);
SELECT set_config('iic.mig_pw', :'mig_pw', false);

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_app') THEN
    EXECUTE format('CREATE ROLE iic_app LOGIN PASSWORD %L', current_setting('iic.app_pw'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_ro') THEN
    EXECUTE format('CREATE ROLE iic_ro LOGIN PASSWORD %L', current_setting('iic.ro_pw'));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_migration') THEN
    EXECUTE format('CREATE ROLE iic_migration LOGIN PASSWORD %L', current_setting('iic.mig_pw'));
  END IF;
END
$$;

-- The migration role needs to create extensions and schemas; treat it like
-- a per-database superuser scoped to this database.
GRANT CREATE ON DATABASE iic TO iic_migration;
GRANT ALL PRIVILEGES ON DATABASE iic TO iic_migration;

-- Postgres 15+ revokes CREATE on schema `public` from PUBLIC. Alembic's
-- version table (`alembic_version`) lands in `public` by default, so the
-- migration role needs CREATE there too.
GRANT USAGE, CREATE ON SCHEMA public TO iic_migration;

-- The application role and read-only role get USAGE on `lake` after the
-- first migration applies (see migration 0001).

-- D7.1 §H2.7 — pre-create pgvector as superuser before any migration tries to.
-- pgvector ships pre-built in timescaledb-ha but is not in the PG trusted-extension
-- allow-list, so iic_migration (non-superuser) cannot CREATE EXTENSION vector
-- on its own. Idempotent: IF NOT EXISTS is a no-op on re-runs.
CREATE EXTENSION IF NOT EXISTS vector;

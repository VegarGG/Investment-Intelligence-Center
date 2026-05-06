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

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_app') THEN
    EXECUTE format('CREATE ROLE iic_app LOGIN PASSWORD %L', :'app_pw');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_ro') THEN
    EXECUTE format('CREATE ROLE iic_ro LOGIN PASSWORD %L', :'ro_pw');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iic_migration') THEN
    EXECUTE format('CREATE ROLE iic_migration LOGIN PASSWORD %L', :'mig_pw');
  END IF;
END
$$;

-- The migration role needs to create extensions and schemas; treat it like
-- a per-database superuser scoped to this database.
GRANT CREATE ON DATABASE iic TO iic_migration;
GRANT ALL PRIVILEGES ON DATABASE iic TO iic_migration;

-- The application role and read-only role get USAGE on `lake` after the
-- first migration applies (see migration 0001).

"""Alembic env — uses sync psycopg2 with the iic_migration role."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from data_lake.config import get_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject DSN at runtime — keeps secrets out of alembic.ini.
config.set_main_option("sqlalchemy.url", get_config().pg_dsn_migration)

target_metadata = None  # we use raw op.execute() — no SQLAlchemy ORM models


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        context.configure(connection=conn)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

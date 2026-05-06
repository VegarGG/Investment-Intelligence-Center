"""Env -> config resolution for every store.

GROUND TRUTH: env keys come from `.env.example` at the repo root. Three Postgres
DSNs (`app`, `ro`, `migration`) map to the three roles in workflow 02 §7.1.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        raise KeyError(f"required env var not set: {key}")
    return val


@dataclass(frozen=True, slots=True)
class LakeConfig:
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user_app: str
    pg_password_app: str
    pg_user_ro: str
    pg_password_ro: str
    pg_user_migration: str
    pg_password_migration: str

    chroma_host: str
    chroma_port: int

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_default: str
    minio_secure: bool

    redis_url: str

    @property
    def pg_dsn_app(self) -> str:
        return self._dsn(self.pg_user_app, self.pg_password_app, async_driver=True)

    @property
    def pg_dsn_ro(self) -> str:
        return self._dsn(self.pg_user_ro, self.pg_password_ro, async_driver=True)

    @property
    def pg_dsn_migration(self) -> str:
        return self._dsn(self.pg_user_migration, self.pg_password_migration, async_driver=False)

    def _dsn(self, user: str, password: str, *, async_driver: bool) -> str:
        driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
        return f"{driver}://{user}:{password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"


@lru_cache(maxsize=1)
def get_config() -> LakeConfig:
    """Resolve once per process. Keys come from `.env.example`."""
    pg_user_app = _env("POSTGRES_USER", "iic_app")
    pg_password_app = _env("POSTGRES_PASSWORD", "")
    return LakeConfig(
        pg_host=_env("POSTGRES_HOST", "postgres"),
        pg_port=int(_env("POSTGRES_PORT", "5432")),
        pg_db=_env("POSTGRES_DB", "iic"),
        pg_user_app=pg_user_app,
        pg_password_app=pg_password_app,
        pg_user_ro=os.environ.get("POSTGRES_USER_RO", "iic_ro"),
        pg_password_ro=os.environ.get("POSTGRES_PASSWORD_RO", pg_password_app),
        pg_user_migration=os.environ.get("POSTGRES_USER_MIGRATION", "iic_migration"),
        pg_password_migration=os.environ.get("POSTGRES_PASSWORD_MIGRATION", pg_password_app),
        chroma_host=_env("CHROMA_HOST", "chroma"),
        chroma_port=int(_env("CHROMA_PORT", "8000")),
        minio_endpoint=_env("MINIO_ENDPOINT", "minio:9000"),
        minio_access_key=_env("MINIO_ROOT_USER", "iic"),
        minio_secret_key=_env("MINIO_ROOT_PASSWORD", ""),
        minio_bucket_default=os.environ.get("MINIO_BUCKET", "iic"),
        minio_secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
        redis_url=_env("REDIS_URL", "redis://redis:6379/0"),
    )

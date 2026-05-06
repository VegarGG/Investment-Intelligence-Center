"""SQLAlchemy 2 async engine + sessionmaker for the lake (workflow 02 §4)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from data_lake.config import get_config

Role = Literal["app", "ro"]


@lru_cache(maxsize=2)
def engine(role: Role = "app") -> AsyncEngine:
    """One engine per role per process. App for read+write, ro for dashboards."""
    cfg = get_config()
    dsn = cfg.pg_dsn_app if role == "app" else cfg.pg_dsn_ro
    return create_async_engine(
        dsn,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=600,
        future=True,
    )


@lru_cache(maxsize=2)
def sessionmaker(role: Role = "app") -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine(role), expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session(role: Role = "app") -> AsyncIterator[AsyncSession]:
    """Context-managed session. Commits on clean exit, rolls back on exception."""
    sm = sessionmaker(role)
    async with sm() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise

"""User preferences store backing lake.user_prefs (P6.4).

Keys the slash commands and outbound notifier read:
  - ``tone``                  — terse | conv | edu
  - ``mute_until``            — ISO datetime; suppress non-critical pushes
  - ``push_frequency``        — brief_only | brief+events | everything
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PrefRow:
    user_id: str
    key: str
    value: str
    expires_at: datetime | None
    updated_at: datetime


class PrefStore(Protocol):
    async def get(self, user_id: str, key: str) -> str | None: ...
    async def set(self, user_id: str, key: str, value: str, *, ttl_seconds: int | None = None) -> None: ...
    async def all_for(self, user_id: str) -> dict[str, str]: ...


class InMemoryPrefStore(PrefStore):
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], PrefRow] = {}

    async def get(self, user_id: str, key: str) -> str | None:
        row = self._rows.get((user_id, key))
        if row is None:
            return None
        if row.expires_at and row.expires_at < datetime.now(UTC):
            return None
        return row.value

    async def set(self, user_id: str, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        )
        self._rows[(user_id, key)] = PrefRow(
            user_id=user_id,
            key=key,
            value=value,
            expires_at=expires_at,
            updated_at=datetime.now(UTC),
        )

    async def all_for(self, user_id: str) -> dict[str, str]:
        now = datetime.now(UTC)
        return {
            r.key: r.value
            for (uid, _), r in self._rows.items()
            if uid == user_id and (r.expires_at is None or r.expires_at > now)
        }


class PostgresPrefStore(PrefStore):
    """Production sink — lake.user_prefs."""

    __slots__ = ("_sm",)

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    @classmethod
    def from_env(cls) -> "PostgresPrefStore":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get("IIC_PG_DSN", "postgresql+asyncpg://iic_app@iic-postgres:5432/iic")
        engine = create_async_engine(url, pool_pre_ping=True)
        return cls(async_sessionmaker(engine, expire_on_commit=False))

    async def get(self, user_id: str, key: str) -> str | None:
        from sqlalchemy import text

        sql = text(
            "SELECT value, expires_at FROM lake.user_prefs "
            "WHERE user_id = :u AND key = :k"
        )
        async with self._sm() as session:  # type: ignore[operator]
            row = (await session.execute(sql, {"u": user_id, "k": key})).first()
        if row is None:
            return None
        if row.expires_at and row.expires_at < datetime.now(UTC):
            return None
        return row.value

    async def set(self, user_id: str, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        from sqlalchemy import text

        sql = text(
            """
            INSERT INTO lake.user_prefs (user_id, key, value, expires_at, updated_at)
            VALUES (:u, :k, :v, :exp, now())
            ON CONFLICT (user_id, key)
            DO UPDATE SET value = EXCLUDED.value,
                          expires_at = EXCLUDED.expires_at,
                          updated_at = now()
            """
        )
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=ttl_seconds) if ttl_seconds else None
        )
        async with self._sm() as session:  # type: ignore[operator]
            await session.execute(sql, {"u": user_id, "k": key, "v": value, "exp": expires_at})
            await session.commit()

    async def all_for(self, user_id: str) -> dict[str, str]:
        from sqlalchemy import text

        sql = text(
            "SELECT key, value, expires_at FROM lake.user_prefs WHERE user_id = :u"
        )
        now = datetime.now(UTC)
        async with self._sm() as session:  # type: ignore[operator]
            rows = (await session.execute(sql, {"u": user_id})).all()
        return {r.key: r.value for r in rows if not r.expires_at or r.expires_at > now}

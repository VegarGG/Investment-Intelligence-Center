"""Conversation memory for the secretary's /chat endpoint (P6.5).

Two backends: InMemory for unit tests, Postgres-backed for production
writing to ``lake.secretary_thread``. Retention is bounded by the
secretary's planner (100 turns / 30 days, enforced when reading) so
the table doesn't grow unbounded.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

Role = Literal["user", "assistant", "system", "tool"]


@dataclass(frozen=True, slots=True)
class ThreadTurn:
    thread_id: str
    ts: datetime
    role: Role
    content: str
    trace_id: str | None = None


class ThreadStore(Protocol):
    async def append(
        self,
        *,
        thread_id: str,
        role: Role,
        content: str,
        trace_id: str | None = None,
    ) -> ThreadTurn: ...

    async def last_n(
        self, thread_id: str, *, n: int = 100, max_age_days: int = 30
    ) -> list[ThreadTurn]: ...


@dataclass
class InMemoryThreadStore(ThreadStore):
    turns: list[ThreadTurn] = field(default_factory=list)

    async def append(
        self,
        *,
        thread_id: str,
        role: Role,
        content: str,
        trace_id: str | None = None,
    ) -> ThreadTurn:
        turn = ThreadTurn(
            thread_id=thread_id,
            ts=datetime.now(UTC),
            role=role,
            content=content,
            trace_id=trace_id,
        )
        self.turns.append(turn)
        return turn

    async def last_n(
        self, thread_id: str, *, n: int = 100, max_age_days: int = 30
    ) -> list[ThreadTurn]:
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        rows = [t for t in self.turns if t.thread_id == thread_id and t.ts >= cutoff]
        return rows[-n:]


class PostgresThreadStore(ThreadStore):
    __slots__ = ("_sm",)

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    @classmethod
    def from_env(cls) -> "PostgresThreadStore":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get(
            "IIC_PG_DSN", "postgresql+asyncpg://iic_app@iic-postgres:5432/iic"
        )
        engine = create_async_engine(url, pool_pre_ping=True)
        return cls(async_sessionmaker(engine, expire_on_commit=False))

    async def append(
        self,
        *,
        thread_id: str,
        role: Role,
        content: str,
        trace_id: str | None = None,
    ) -> ThreadTurn:
        from sqlalchemy import text

        ts = datetime.now(UTC)
        sql = text(
            """
            INSERT INTO lake.secretary_thread (thread_id, ts, role, content, trace_id)
            VALUES (:thread_id, :ts, :role, :content, :trace_id)
            """
        )
        async with self._sm() as session:  # type: ignore[operator]
            await session.execute(
                sql,
                {
                    "thread_id": thread_id,
                    "ts": ts,
                    "role": role,
                    "content": content,
                    "trace_id": trace_id,
                },
            )
            await session.commit()
        return ThreadTurn(
            thread_id=thread_id, ts=ts, role=role, content=content, trace_id=trace_id
        )

    async def last_n(
        self, thread_id: str, *, n: int = 100, max_age_days: int = 30
    ) -> list[ThreadTurn]:
        from sqlalchemy import text

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        sql = text(
            """
            SELECT thread_id, ts, role, content, trace_id
              FROM lake.secretary_thread
             WHERE thread_id = :tid
               AND ts >= :cutoff
             ORDER BY ts ASC
             LIMIT :n
            """
        )
        async with self._sm() as session:  # type: ignore[operator]
            rows = (
                await session.execute(
                    sql, {"tid": thread_id, "cutoff": cutoff, "n": n}
                )
            ).all()
        return [
            ThreadTurn(
                thread_id=r.thread_id,
                ts=r.ts,
                role=r.role,
                content=r.content,
                trace_id=r.trace_id,
            )
            for r in rows
        ]

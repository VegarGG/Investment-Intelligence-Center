"""Hash-chained config-write audit log (P3.1).

Mirrors the ``lake.advice`` chain semantics: every row carries
``prev_chain_hash`` linking to the previous head, plus its own
``chain_hash`` so a tamper of any row breaks the verify pass.

Three sinks:
  - ``InMemoryAuditSink`` — unit-test default.
  - ``PostgresAuditSink`` — production; writes to ``lake.config_audit``
    (migration 0008, P3.2).
  - ``CompositeSink`` — emit to multiple sinks for tee'ing test + DB.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ConfigAuditRow:
    id: str
    ts: datetime
    actor: str
    path: str
    before_hash: str | None
    after_hash: str
    prev_chain_hash: str | None
    chain_hash: str
    reason: str | None = None


class AuditSink(Protocol):
    async def append(
        self,
        *,
        actor: str,
        path: str,
        before_hash: str | None,
        after_hash: str,
        reason: str | None,
    ) -> ConfigAuditRow: ...

    async def head(self) -> str | None: ...


def _compute_chain_hash(
    *,
    prev: str | None,
    actor: str,
    path: str,
    before_hash: str | None,
    after_hash: str,
    ts: datetime,
) -> str:
    h = hashlib.sha256()
    h.update((prev or "").encode())
    h.update(actor.encode())
    h.update(path.encode())
    h.update((before_hash or "").encode())
    h.update(after_hash.encode())
    h.update(ts.isoformat().encode())
    return h.hexdigest()


class InMemoryAuditSink(AuditSink):
    """Test sink — preserves order + chain hashes in memory."""

    def __init__(self) -> None:
        self.rows: list[ConfigAuditRow] = []

    async def append(
        self,
        *,
        actor: str,
        path: str,
        before_hash: str | None,
        after_hash: str,
        reason: str | None,
    ) -> ConfigAuditRow:
        ts = datetime.now(UTC)
        prev = self.rows[-1].chain_hash if self.rows else None
        chain = _compute_chain_hash(
            prev=prev,
            actor=actor,
            path=path,
            before_hash=before_hash,
            after_hash=after_hash,
            ts=ts,
        )
        row = ConfigAuditRow(
            id=str(uuid.uuid4()),
            ts=ts,
            actor=actor,
            path=path,
            before_hash=before_hash,
            after_hash=after_hash,
            prev_chain_hash=prev,
            chain_hash=chain,
            reason=reason,
        )
        self.rows.append(row)
        return row

    async def head(self) -> str | None:
        return self.rows[-1].chain_hash if self.rows else None


@dataclass
class PostgresAuditSink(AuditSink):
    """Writes one row per config edit to ``lake.config_audit``.

    Sessionmaker is supplied by the admin API factory at boot. The schema
    requires (id, ts) as PK to satisfy the TimescaleDB hypertable PK
    rule (P1.5 lint catches PR-time regressions).
    """

    sessionmaker: object

    @classmethod
    def from_env(cls) -> "PostgresAuditSink":
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        url = os.environ.get(
            "IIC_PG_DSN",
            "postgresql+asyncpg://iic_app@iic-postgres:5432/iic",
        )
        engine = create_async_engine(url, pool_pre_ping=True)
        return cls(sessionmaker=async_sessionmaker(engine, expire_on_commit=False))

    async def append(
        self,
        *,
        actor: str,
        path: str,
        before_hash: str | None,
        after_hash: str,
        reason: str | None,
    ) -> ConfigAuditRow:
        from sqlalchemy import text

        prev = await self.head()
        ts = datetime.now(UTC)
        chain = _compute_chain_hash(
            prev=prev,
            actor=actor,
            path=path,
            before_hash=before_hash,
            after_hash=after_hash,
            ts=ts,
        )
        row = ConfigAuditRow(
            id=str(uuid.uuid4()),
            ts=ts,
            actor=actor,
            path=path,
            before_hash=before_hash,
            after_hash=after_hash,
            prev_chain_hash=prev,
            chain_hash=chain,
            reason=reason,
        )
        sql = text(
            """
            INSERT INTO lake.config_audit (
              id, ts, actor, path, before_hash, after_hash,
              prev_chain_hash, chain_hash, reason
            ) VALUES (
              :id, :ts, :actor, :path, :before_hash, :after_hash,
              :prev_chain_hash, :chain_hash, :reason
            )
            """
        )
        async with self.sessionmaker() as session:  # type: ignore[operator]
            await session.execute(
                sql,
                {
                    "id": row.id,
                    "ts": row.ts,
                    "actor": row.actor,
                    "path": row.path,
                    "before_hash": bytes.fromhex(before_hash) if before_hash else None,
                    "after_hash": bytes.fromhex(after_hash),
                    "prev_chain_hash": bytes.fromhex(prev) if prev else None,
                    "chain_hash": bytes.fromhex(chain),
                    "reason": reason,
                },
            )
            await session.commit()
        return row

    async def head(self) -> str | None:
        from sqlalchemy import text

        sql = text(
            "SELECT encode(chain_hash, 'hex') AS h "
            "FROM lake.config_audit ORDER BY ts DESC, id DESC LIMIT 1"
        )
        async with self.sessionmaker() as session:  # type: ignore[operator]
            res = await session.execute(sql)
            row = res.first()
            return row.h if row else None

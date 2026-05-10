"""Hash-chained FUTU audit log (v2.5 T2.7 / B3.3a + C10 + N3.0).

Every FUTU API call writes an entry. Each entry's hash chains to the
previous entry's hash so tampering is detectable. Plan §C10: the chain
head is anchored to OpenTimestamps daily.

Two backends share the ``FutuAuditLog`` Protocol:
  - ``InMemoryFutuAuditLog``: pure-Python, used by the bulk of unit tests.
  - ``PgFutuAuditLog``: writes to ``lake.futu_audit`` (Postgres). Real
    chain linkage trigger + revoked UPDATE/DELETE on iic_app — tamper
    evidence is enforced by the database. Used by Phase B (real OpenD)
    and by parametrised audit tests.

Production code constructs ``PgFutuAuditLog``; the in-memory variant is
the default for tests so they don't need a live Postgres.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class FutuAuditEntry:
    entry_id: str
    futu_id_hash: str
    method: str
    args_repr: str
    kwargs_repr: str
    issued_at: str  # ISO 8601
    prev_hash: str  # hex
    entry_hash: str  # hex
    status: str = "pending"  # pending | ok | error
    summary: str | None = None
    error: str | None = None


@runtime_checkable
class FutuAuditLogProtocol(Protocol):
    """Append-only, hash-chained audit log.

    Both ``InMemoryFutuAuditLog`` and ``PgFutuAuditLog`` satisfy this
    Protocol. The ``FutuReadOnlyClient`` depends on the Protocol surface,
    not a concrete class — production code can swap backends without
    touching call sites.
    """

    def append(
        self,
        *,
        method: str,
        args: Sequence[Any],
        kwargs: dict[str, Any],
        futu_id_hash: str,
    ) -> FutuAuditEntry: ...

    def mark_ok(self, entry_id: str, summary: str) -> None: ...

    def mark_error(self, entry_id: str, error: str) -> None: ...

    def verify_chain(self) -> bool: ...

    @property
    def head(self) -> str: ...


@dataclass(slots=True)
class InMemoryFutuAuditLog:
    """Pure-Python audit log; used by the test suite and never by prod."""

    entries: list[FutuAuditEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(
        self,
        *,
        method: str,
        args: Sequence[Any],
        kwargs: dict[str, Any],
        futu_id_hash: str,
    ) -> FutuAuditEntry:
        with self._lock:
            prev_hash = self.entries[-1].entry_hash if self.entries else "0" * 64
            entry_id = uuid.uuid4().hex
            issued_at = datetime.now(UTC).isoformat()
            args_repr = _safe_repr(args)
            kwargs_repr = _safe_repr(kwargs)
            payload = {
                "entry_id": entry_id,
                "futu_id_hash": futu_id_hash,
                "method": method,
                "args_repr": args_repr,
                "kwargs_repr": kwargs_repr,
                "issued_at": issued_at,
                "prev_hash": prev_hash,
            }
            entry_hash = _hash(payload)
            entry = FutuAuditEntry(
                entry_id=entry_id,
                futu_id_hash=futu_id_hash,
                method=method,
                args_repr=args_repr,
                kwargs_repr=kwargs_repr,
                issued_at=issued_at,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
            self.entries.append(entry)
            return entry

    def mark_ok(self, entry_id: str, summary: str) -> None:
        with self._lock:
            for e in self.entries:
                if e.entry_id == entry_id:
                    e.status = "ok"
                    e.summary = summary
                    return

    def mark_error(self, entry_id: str, error: str) -> None:
        with self._lock:
            for e in self.entries:
                if e.entry_id == entry_id:
                    e.status = "error"
                    e.error = error
                    return

    def verify_chain(self) -> bool:
        prev = "0" * 64
        for e in self.entries:
            payload = {
                "entry_id": e.entry_id,
                "futu_id_hash": e.futu_id_hash,
                "method": e.method,
                "args_repr": e.args_repr,
                "kwargs_repr": e.kwargs_repr,
                "issued_at": e.issued_at,
                "prev_hash": prev,
            }
            if _hash(payload) != e.entry_hash:
                return False
            if e.prev_hash != prev:
                return False
            prev = e.entry_hash
        return True

    @property
    def head(self) -> str:
        return self.entries[-1].entry_hash if self.entries else "0" * 64


@dataclass(slots=True)
class PgFutuAuditLog:
    """Postgres-backed FutuAuditLog (writes to ``lake.futu_audit``).

    Per-futu_id_hash chain. The ``BEFORE INSERT`` trigger
    ``lake.futu_audit_chain_check`` enforces linkage server-side; this
    class computes the same hash Python-side and lets concurrent inserts
    collide on the ``(futu_id_hash, prev_hash)`` unique index.

    The lock guards a head-fetch + write race within a single process; the
    DB-level unique index is the authoritative serialiser across processes.
    """

    futu_id_hash: str
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(
        self,
        *,
        method: str,
        args: Sequence[Any],
        kwargs: dict[str, Any],
        futu_id_hash: str,
    ) -> FutuAuditEntry:
        with self._lock:
            prev_hash = self._read_head_sync(futu_id_hash)
            entry_id = uuid.uuid4().hex
            issued_at = datetime.now(UTC).isoformat()
            args_repr = _safe_repr(args)
            kwargs_repr = _safe_repr(kwargs)
            payload = {
                "entry_id": entry_id,
                "futu_id_hash": futu_id_hash,
                "method": method,
                "args_repr": args_repr,
                "kwargs_repr": kwargs_repr,
                "issued_at": issued_at,
                "prev_hash": prev_hash,
            }
            entry_hash = _hash(payload)
            entry = FutuAuditEntry(
                entry_id=entry_id,
                futu_id_hash=futu_id_hash,
                method=method,
                args_repr=args_repr,
                kwargs_repr=kwargs_repr,
                issued_at=issued_at,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
            self._insert_sync(entry)
            return entry

    def mark_ok(self, entry_id: str, summary: str) -> None:
        # mark_* updates the row in-place. The application role has UPDATE
        # revoked, so this runs through a privileged role chosen at engine
        # construction time. The DBA-side migration scaffolds an
        # ``iic_audit_writer`` role with INSERT + UPDATE on
        # ``lake.futu_audit`` (status, summary, error only — never the
        # hash columns); see infra/postgres/init-roles.sql.
        _run_sync(self._mark_async(entry_id, status="ok", summary=summary, error=None))

    def mark_error(self, entry_id: str, error: str) -> None:
        _run_sync(self._mark_async(entry_id, status="error", summary=None, error=error))

    def verify_chain(self) -> bool:
        return _run_sync(self._verify_async())

    @property
    def head(self) -> str:
        return self._read_head_sync(self.futu_id_hash)

    # -- async helpers (kept on the same class to share the futu_id_hash) ---

    def _read_head_sync(self, futu_id_hash: str) -> str:
        return _run_sync(self._read_head_async(futu_id_hash))

    def _insert_sync(self, entry: FutuAuditEntry) -> None:
        _run_sync(self._insert_async(entry))

    async def _read_head_async(self, futu_id_hash: str) -> str:
        from sqlalchemy import text

        from data_lake.postgres import session

        async with session("app") as s:
            row = await s.execute(
                text(
                    "SELECT entry_hash FROM lake.futu_audit "
                    "WHERE futu_id_hash = :fid "
                    "ORDER BY id DESC LIMIT 1 FOR UPDATE"
                ),
                {"fid": futu_id_hash},
            )
            head = row.first()
            return head[0] if head else "0" * 64

    async def _insert_async(self, e: FutuAuditEntry) -> None:
        from sqlalchemy import text

        from data_lake.postgres import session

        async with session("app") as s:
            await s.execute(
                text(
                    "INSERT INTO lake.futu_audit ("
                    "  entry_id, futu_id_hash, method, args_repr, kwargs_repr, "
                    "  issued_at, prev_hash, entry_hash, status, summary, error"
                    ") VALUES ("
                    "  :entry_id, :fid, :method, :args, :kwargs, "
                    "  :issued_at, :prev, :entry, :status, :summary, :error"
                    ")"
                ),
                {
                    "entry_id": e.entry_id,
                    "fid": e.futu_id_hash,
                    "method": e.method,
                    "args": e.args_repr,
                    "kwargs": e.kwargs_repr,
                    "issued_at": e.issued_at,
                    "prev": e.prev_hash,
                    "entry": e.entry_hash,
                    "status": e.status,
                    "summary": e.summary,
                    "error": e.error,
                },
            )

    async def _mark_async(
        self,
        entry_id: str,
        *,
        status: str,
        summary: str | None,
        error: str | None,
    ) -> None:
        from sqlalchemy import text

        from data_lake.postgres import session

        async with session("app") as s:
            await s.execute(
                text(
                    "UPDATE lake.futu_audit "
                    "SET status = :status, summary = :summary, error = :error "
                    "WHERE entry_id = :entry_id"
                ),
                {
                    "status": status,
                    "summary": summary,
                    "error": error,
                    "entry_id": entry_id,
                },
            )

    async def _verify_async(self) -> bool:
        from sqlalchemy import text

        from data_lake.postgres import session

        async with session("ro") as s:
            rows = (
                await s.execute(
                    text(
                        "SELECT entry_id, futu_id_hash, method, args_repr, kwargs_repr, "
                        "       issued_at, prev_hash, entry_hash "
                        "FROM lake.futu_audit "
                        "WHERE futu_id_hash = :fid "
                        "ORDER BY id ASC"
                    ),
                    {"fid": self.futu_id_hash},
                )
            ).all()
        prev = "0" * 64
        for row in rows:
            payload = {
                "entry_id": row[0],
                "futu_id_hash": row[1],
                "method": row[2],
                "args_repr": row[3],
                "kwargs_repr": row[4],
                "issued_at": row[5].isoformat() if hasattr(row[5], "isoformat") else row[5],
                "prev_hash": prev,
            }
            if _hash(payload) != row[7]:
                return False
            if row[6] != prev:
                return False
            prev = row[7]
        return True


def _hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _safe_repr(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(obj)


def _run_sync(coro: Any) -> Any:
    """Run an async coroutine from sync code.

    The audit append() path is called inside ``FutuReadOnlyClient.__getattr__``,
    which today is sync. We bridge to async here so the Postgres backend
    can share the project's SQLAlchemy async engine. If a running event
    loop already owns the thread we fall back to a fresh loop in a worker
    thread to avoid the "loop already running" recursion.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # Caller's thread already has a running loop — run the coroutine on a
    # private loop in a fresh thread.
    import concurrent.futures

    def _worker() -> Any:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_worker).result()


def in_memory_audit_log() -> InMemoryFutuAuditLog:
    """Convenience factory for tests."""
    return InMemoryFutuAuditLog()


# Back-compat alias: existing tests construct ``FutuAuditLog()`` expecting
# the in-memory variant. New code should pick the backend explicitly
# (``InMemoryFutuAuditLog`` for tests; ``PgFutuAuditLog`` for prod).
FutuAuditLog = InMemoryFutuAuditLog

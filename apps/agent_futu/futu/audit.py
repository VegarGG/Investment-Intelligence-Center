"""Hash-chained FUTU audit log (v2.5 T2.7 / B3.3a + C10).

Every FUTU API call writes an entry. Each entry's hash chains to the
previous entry's hash so tampering is detectable. Plan §C10: the chain
head is anchored to OpenTimestamps daily.

This module ships the in-memory implementation used by tests; the
production Postgres-backed implementation will land alongside the
schema migration in B3.3b.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


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


@dataclass(slots=True)
class FutuAuditLog:
    """Append-only, hash-chained audit log.

    Production swaps this for `lake.futu_audit` (Postgres) with the same
    semantic surface. Tests use the in-memory variant directly.
    """

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
        """Recompute every hash; return True iff every link verifies."""
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


def _hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _safe_repr(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(obj)


def in_memory_audit_log() -> FutuAuditLog:
    """Convenience factory for tests."""
    return FutuAuditLog()

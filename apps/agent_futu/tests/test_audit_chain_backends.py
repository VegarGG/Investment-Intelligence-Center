"""v2.5 N3.0 — parametrised audit-chain tests over both backends.

The in-memory backend always runs. The Postgres-backed backend
(``PgFutuAuditLog`` + ``lake.futu_audit``) is exercised only when
``IIC_RUN_PG_AUDIT=1`` and a reachable lake database is configured.
The CI walks the in-memory path on every PR; the chaos drill (and the
Mac mini host running the real burn-in) walks the Postgres path.

If you add a new test here, write it against ``log: FutuAuditLogProtocol``
so it runs unmodified against both implementations.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from typing import cast

import pytest
from futu.audit import (
    FutuAuditLogProtocol,
    InMemoryFutuAuditLog,
    PgFutuAuditLog,
)


_PG_ENABLED = os.environ.get("IIC_RUN_PG_AUDIT") == "1"


def _make_in_memory(_fid: str) -> FutuAuditLogProtocol:
    return InMemoryFutuAuditLog()


def _make_pg(fid: str) -> FutuAuditLogProtocol:
    return PgFutuAuditLog(futu_id_hash=fid)


_BACKENDS: list[tuple[str, Callable[[str], FutuAuditLogProtocol]]] = [
    ("in_memory", _make_in_memory),
]
if _PG_ENABLED:
    _BACKENDS.append(("postgres", _make_pg))


@pytest.fixture(params=_BACKENDS, ids=[name for name, _ in _BACKENDS])
def audit_log(request: pytest.FixtureRequest) -> FutuAuditLogProtocol:
    _name, factory = request.param
    # Unique futu_id_hash per test to keep the Postgres rows isolated
    # (both backends accept the value; in-memory ignores it for storage).
    fid = f"fid_test_{uuid.uuid4().hex[:8]}"
    return factory(fid)


def test_initial_chain_head_is_zero(audit_log: FutuAuditLogProtocol) -> None:
    assert audit_log.head == "0" * 64
    assert audit_log.verify_chain() is True


def test_two_appends_link_correctly(audit_log: FutuAuditLogProtocol) -> None:
    fid = _fid_of(audit_log)
    e1 = audit_log.append(method="get_acc_list", args=(), kwargs={}, futu_id_hash=fid)
    e2 = audit_log.append(
        method="position_list_query",
        args=("acc-001",),
        kwargs={},
        futu_id_hash=fid,
    )
    assert e1.prev_hash == "0" * 64
    assert e2.prev_hash == e1.entry_hash
    assert audit_log.head == e2.entry_hash
    assert audit_log.verify_chain() is True


def test_mark_ok_does_not_break_chain(audit_log: FutuAuditLogProtocol) -> None:
    fid = _fid_of(audit_log)
    e = audit_log.append(method="get_acc_list", args=(), kwargs={}, futu_id_hash=fid)
    audit_log.mark_ok(e.entry_id, "ok=0 rows=2")
    assert audit_log.verify_chain() is True


def test_mark_error_does_not_break_chain(audit_log: FutuAuditLogProtocol) -> None:
    fid = _fid_of(audit_log)
    e = audit_log.append(method="get_acc_list", args=(), kwargs={}, futu_id_hash=fid)
    audit_log.mark_error(e.entry_id, "network down")
    assert audit_log.verify_chain() is True


def test_chain_head_advances_monotonically(audit_log: FutuAuditLogProtocol) -> None:
    fid = _fid_of(audit_log)
    h0 = audit_log.head
    audit_log.append(method="get_acc_list", args=(), kwargs={}, futu_id_hash=fid)
    h1 = audit_log.head
    audit_log.append(method="get_market_state", args=(["US.AAPL"],), kwargs={}, futu_id_hash=fid)
    h2 = audit_log.head
    assert h0 == "0" * 64
    assert h0 != h1 != h2


@pytest.mark.skipif(not _PG_ENABLED, reason="IIC_RUN_PG_AUDIT not set")
def test_postgres_trigger_rejects_fabricated_prev_hash() -> None:
    """The BEFORE INSERT trigger refuses non-head rows whose prev_hash is bogus."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from data_lake.postgres import session

    async def _attempt() -> None:
        async with session("app") as s:
            await s.execute(
                text(
                    "INSERT INTO lake.futu_audit ("
                    "  entry_id, futu_id_hash, method, args_repr, kwargs_repr, "
                    "  issued_at, prev_hash, entry_hash"
                    ") VALUES ("
                    "  :eid, :fid, 'get_acc_list', '[]', '{}', now(), :prev, :eh"
                    ")"
                ),
                {
                    "eid": uuid.uuid4().hex,
                    "fid": f"fid_pen_{uuid.uuid4().hex[:8]}",
                    # Non-head row (not the all-zero sentinel) pointing at a
                    # value that doesn't exist anywhere in the table.
                    "prev": "f" * 64,
                    "eh": "a" * 64,
                },
            )

    with pytest.raises(IntegrityError):
        asyncio.run(_attempt())


def _fid_of(log: FutuAuditLogProtocol) -> str:
    pg = cast(PgFutuAuditLog, log) if isinstance(log, PgFutuAuditLog) else None
    if pg is not None:
        return pg.futu_id_hash
    return f"fid_in_mem_{uuid.uuid4().hex[:8]}"

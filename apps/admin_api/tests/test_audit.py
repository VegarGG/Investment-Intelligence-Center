"""P3.1 — hash-chained audit log."""

from __future__ import annotations

import pytest

from admin_api import audit


@pytest.mark.asyncio
async def test_chain_links_each_row_to_previous_head():
    sink = audit.InMemoryAuditSink()
    a = await sink.append(actor="alice", path="x.yaml", before_hash=None, after_hash="aa", reason=None)
    b = await sink.append(actor="alice", path="x.yaml", before_hash="aa", after_hash="bb", reason=None)
    c = await sink.append(actor="bob", path="y.yaml", before_hash=None, after_hash="cc", reason=None)
    assert b.prev_chain_hash == a.chain_hash
    assert c.prev_chain_hash == b.chain_hash


@pytest.mark.asyncio
async def test_head_tracks_latest():
    sink = audit.InMemoryAuditSink()
    assert await sink.head() is None
    row = await sink.append(actor="x", path="p", before_hash=None, after_hash="d", reason="r")
    assert await sink.head() == row.chain_hash


@pytest.mark.asyncio
async def test_chain_hash_stable_under_replay():
    """Recomputing the chain hash from the row's recorded fields must match."""
    sink = audit.InMemoryAuditSink()
    a = await sink.append(actor="alice", path="x.yaml", before_hash=None, after_hash="aa", reason=None)
    recomputed = audit._compute_chain_hash(  # noqa: SLF001 — test invariant
        prev=a.prev_chain_hash,
        actor=a.actor,
        path=a.path,
        before_hash=a.before_hash,
        after_hash=a.after_hash,
        ts=a.ts,
    )
    assert recomputed == a.chain_hash

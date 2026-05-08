"""v2.5 T2.7 / B3.3a + C10 — FUTU audit chain tamper-evidence."""

from __future__ import annotations

import pytest
from futu.audit import FutuAuditLog
from futu.fake_opend import make_fake_openD_pair
from futu.readonly_client import FutuReadOnlyClient


def _client_with_audit():
    audit = FutuAuditLog()
    fake_a, _ = make_fake_openD_pair()
    return FutuReadOnlyClient(openD=fake_a, futu_id_hash="fid_test", audit=audit), audit


def test_initial_chain_head_is_zero():
    audit = FutuAuditLog()
    assert audit.head == "0" * 64
    assert audit.verify_chain() is True


def test_chain_links_correctly_across_n_calls():
    c, audit = _client_with_audit()
    c.get_acc_list()
    c.position_list_query("acc-001")
    c.get_market_state(["US.AAPL"])
    assert len(audit.entries) == 3
    # Each entry's prev_hash is the previous entry's entry_hash.
    for prev, curr in zip(audit.entries, audit.entries[1:]):
        assert curr.prev_hash == prev.entry_hash
    assert audit.verify_chain() is True


def test_tampering_with_method_breaks_chain():
    c, audit = _client_with_audit()
    c.get_acc_list()
    c.position_list_query("acc-001")
    # Alice tampers: changes a method name without recomputing the hash.
    audit.entries[0].method = "place_order"
    assert audit.verify_chain() is False


def test_tampering_with_args_breaks_chain():
    c, audit = _client_with_audit()
    c.position_list_query("acc-001")
    audit.entries[0].args_repr = '["acc-evil"]'
    assert audit.verify_chain() is False


def test_reordering_breaks_chain():
    c, audit = _client_with_audit()
    c.get_acc_list()
    c.position_list_query("acc-001")
    audit.entries.reverse()
    assert audit.verify_chain() is False


def test_chain_head_advances_monotonically():
    c, audit = _client_with_audit()
    h0 = audit.head
    c.get_acc_list()
    h1 = audit.head
    c.position_list_query("acc-001")
    h2 = audit.head
    assert h0 != h1
    assert h1 != h2


def test_error_calls_recorded_with_status_error():
    """Even if the underlying SDK raises, the audit trail captures the attempt."""
    audit = FutuAuditLog()

    class ExplodingOpenD:
        def get_market_state(self, codes):
            raise RuntimeError("network down")

    c = FutuReadOnlyClient(openD=ExplodingOpenD(), futu_id_hash="fid_test", audit=audit)
    with pytest.raises(RuntimeError):
        c.get_market_state(["US.AAPL"])
    assert len(audit.entries) == 1
    assert audit.entries[0].status == "error"
    assert "network down" in (audit.entries[0].error or "")
    # And the chain is still intact (errors don't break tamper-evidence).
    assert audit.verify_chain() is True


def test_aggregator_round_trip_validates_schema():
    """End-to-end: build a snapshot from the fakes, validate it as a Pydantic model."""
    from futu.aggregator import aggregate_snapshot
    from futu.audit import FutuAuditLog

    audit = FutuAuditLog()
    a, b = make_fake_openD_pair()
    clients = [
        FutuReadOnlyClient(openD=a, futu_id_hash="fid_a", audit=audit),
        FutuReadOnlyClient(openD=b, futu_id_hash="fid_b", audit=audit),
    ]
    snap = aggregate_snapshot(clients)
    assert len(snap.accounts) == 2
    assert snap.aggregate.nav_base_ccy > 0
    # 5 positions per account = 10 total
    total = sum(len(a.positions) for a in snap.accounts)
    assert total == 10
    # Audit chain is still intact after the aggregate read.
    assert audit.verify_chain() is True

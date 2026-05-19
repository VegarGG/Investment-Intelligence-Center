"""v2.5 T2.7 / B3.3a — FutuReadOnlyClient enforces read-only at every layer.

DREADFUL-LIMITATION TESTS — these must stay green or the wrapper is unsafe.
Plan §T2.7: real-integration variant in B3.3b will additionally exercise
the firewall + the absence of `unlock_trade()` against a paper account.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from futu.audit import FutuAuditLog
from futu.fake_opend import make_fake_openD_pair
from futu.readonly_client import (
    ALLOWED_METHODS,
    FORBIDDEN_METHODS,
    FutuReadOnlyClient,
    FutuReadOnlyError,
)


def _client():
    fake_a, _ = make_fake_openD_pair()
    return FutuReadOnlyClient(openD=fake_a, futu_id_hash="fid_test", audit=FutuAuditLog())


def test_allowlist_is_subset_of_known_safe_methods():
    """Adding to ALLOWED_METHODS requires a security-review entry."""
    safe = {
        "get_acc_list",
        "accinfo_query",
        "position_list_query",
        "order_list_query",
        "history_order_list_query",
        "history_deal_list_query",
        "get_market_state",
    }
    assert ALLOWED_METHODS == safe


def test_forbidden_methods_set_includes_every_mutating_call():
    must_be_forbidden = {"place_order", "modify_order", "cancel_order", "unlock_trade"}
    assert must_be_forbidden.issubset(FORBIDDEN_METHODS)


def test_calling_place_order_raises_FutuReadOnlyError():
    c = _client()
    with pytest.raises(FutuReadOnlyError) as exc:
        c.place_order(price=100, code="US.AAPL")
    assert "place_order" in str(exc.value)
    assert "read-only" in str(exc.value)


def test_calling_unlock_trade_raises_FutuReadOnlyError():
    c = _client()
    with pytest.raises(FutuReadOnlyError):
        c.unlock_trade(password="anything")


def test_calling_modify_order_raises_FutuReadOnlyError():
    c = _client()
    with pytest.raises(FutuReadOnlyError):
        c.modify_order(order_id="x", price=100)


def test_calling_cancel_order_raises_FutuReadOnlyError():
    c = _client()
    with pytest.raises(FutuReadOnlyError):
        c.cancel_order(order_id="x")


def test_unknown_method_raises_AttributeError():
    """Unknown methods raise AttributeError so callers don't silently fall through."""
    c = _client()
    with pytest.raises(AttributeError):
        c.deposit_money(amount=1000)


def test_allowed_method_returns_real_data():
    c = _client()
    ret, accs = c.get_acc_list()
    assert ret == 0
    assert len(accs) >= 1


def test_allowed_method_writes_audit_entry():
    audit = FutuAuditLog()
    fake_a, _ = make_fake_openD_pair()
    c = FutuReadOnlyClient(openD=fake_a, futu_id_hash="fid_test", audit=audit)

    assert len(audit.entries) == 0
    c.get_acc_list()
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry.method == "get_acc_list"
    assert entry.status == "ok"
    assert entry.futu_id_hash == "fid_test"


def test_forbidden_call_does_NOT_write_audit_entry():
    """Reject before audit — audit-log spam is not a vector we want."""
    audit = FutuAuditLog()
    fake_a, _ = make_fake_openD_pair()
    c = FutuReadOnlyClient(openD=fake_a, futu_id_hash="fid_test", audit=audit)

    with pytest.raises(FutuReadOnlyError):
        c.place_order(price=100)
    assert len(audit.entries) == 0


def test_no_non_test_code_imports_forbidden_methods():
    """Static-check: no production file references any forbidden method by name.

    This is the bandit/mypy-style guard the plan §T2.7 requires.
    """
    from featureflags.paths import repo_root as _repo_root

    repo_root = _repo_root()
    scan_paths = (
        repo_root / "apps",
        repo_root / "packages",
    )
    forbidden_names = sorted(FORBIDDEN_METHODS)
    offenders: list[tuple[str, str]] = []
    for root in scan_paths:
        for py in root.rglob("*.py"):
            # Skip tests, the wrapper itself (where the names are documented),
            # and the FakeOpenD fixture (test-only).
            parts = py.relative_to(repo_root).parts
            if "tests" in parts:
                continue
            if py.name in {"readonly_client.py", "fake_opend.py"}:
                continue
            try:
                text = py.read_text()
            except OSError:
                continue
            for name in forbidden_names:
                if f".{name}(" in text or f" {name}(" in text:
                    offenders.append((str(py.relative_to(repo_root)), name))
    assert not offenders, (
        "Forbidden FUTU method referenced in non-test code: "
        + ", ".join(f"{p}::{n}" for p, n in offenders)
    )

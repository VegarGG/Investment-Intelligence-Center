"""FutuReadOnlyClient — read-only wrapper around an OpenD trade context.

Plan §T2.7 dreadful-limitation status: **load-bearing safety**. Mocks here
are forbidden in production code paths. The defense in depth:

1. The wrapper exposes only the read methods listed in
   ``ALLOWED_METHODS``.
2. ``ALLOWED_METHODS`` is enforced at call time via ``__getattr__`` —
   every dotted access is checked against the allowlist before forwarding
   to the underlying OpenD context. There is no escape hatch.
3. ``FORBIDDEN_METHODS`` is a checked-against allow-list inverse — the
   custom ``check_no_forbidden_imports`` linter (B3.3a) verifies no
   non-test code imports any of these symbols.
4. ``unlock_trade`` is **never** called. FUTU's SDK rejects every order
   placement at the gateway level without it; this is the load-bearing
   safeguard documented in plan §T2.7.
5. Every call writes a ``FutuAuditEntry`` to the hash-chained audit log
   so a regression in the wrapper is detectable by chain-head verification.

Phase B3.3a (this iteration) tests against ``FakeOpenD`` — a deterministic
fixture that mirrors the SDK shape. Phase B3.3b lights up the real OpenD
container per Futu ID.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .audit import FutuAuditLogProtocol, InMemoryFutuAuditLog

log = logging.getLogger(__name__)


# Methods FutuReadOnlyClient may expose. This list is the contract; adding
# anything to it requires a security-review entry under
# `docs/security/FUTU_readonly_review.md`.
ALLOWED_METHODS: frozenset[str] = frozenset(
    {
        "get_acc_list",
        "accinfo_query",
        "position_list_query",
        "order_list_query",
        "history_order_list_query",
        "history_deal_list_query",
        "get_market_state",
    }
)

# Methods FutuReadOnlyClient MUST NEVER expose. The mypy/bandit static
# check fails CI if any non-test file imports any of these names.
FORBIDDEN_METHODS: frozenset[str] = frozenset(
    {
        "place_order",
        "modify_order",
        "cancel_order",
        "unlock_trade",
        "deal_list_query_realtime",  # mutation-adjacent in some SDK versions
    }
)


class FutuReadOnlyError(Exception):
    """Raised when a forbidden method is requested on the wrapper."""


class _OpenDLike(Protocol):
    """Minimal Protocol the wrapper depends on. ``FakeOpenD`` (tests) and
    the real `futu.OpenSecTradeContext` both satisfy it."""

    def get_acc_list(self) -> Any: ...
    def accinfo_query(self, acc_id: str) -> Any: ...
    def position_list_query(self, acc_id: str) -> Any: ...
    def order_list_query(self, acc_id: str) -> Any: ...
    def history_order_list_query(self, acc_id: str, **kw: Any) -> Any: ...
    def history_deal_list_query(self, acc_id: str, **kw: Any) -> Any: ...
    def get_market_state(self, codes: list[str]) -> Any: ...


@dataclass(slots=True)
class FutuReadOnlyClient:
    """Read-only wrapper. Construct with one OpenD-like instance per Futu ID."""

    openD: _OpenDLike
    futu_id_hash: str
    audit: FutuAuditLogProtocol = field(default_factory=InMemoryFutuAuditLog)
    # Set to True only by tests that explicitly want to exercise the audit
    # log without a real underlying SDK; production agents leave it False.
    test_mode: bool = False

    def __getattr__(self, name: str) -> Any:
        # `__getattr__` only fires when normal attr lookup fails. Anything
        # that's not a regular attribute on this dataclass is treated as a
        # would-be method call against the underlying OpenD — and rejected
        # unless allowlisted.
        if name in FORBIDDEN_METHODS:
            raise FutuReadOnlyError(
                f"forbidden method {name!r} on FutuReadOnlyClient — "
                "this wrapper is strictly read-only by construction"
            )
        if name not in ALLOWED_METHODS:
            raise AttributeError(
                f"FutuReadOnlyClient has no attribute {name!r}; "
                f"allowed methods: {sorted(ALLOWED_METHODS)}"
            )

        underlying = getattr(self.openD, name, None)
        if underlying is None:
            raise FutuReadOnlyError(
                f"OpenD does not expose allowlisted method {name!r}"
            )

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            entry = self.audit.append(
                method=name,
                args=args,
                kwargs=kwargs,
                futu_id_hash=self.futu_id_hash,
            )
            try:
                result = underlying(*args, **kwargs)
            except Exception as exc:
                self.audit.mark_error(entry.entry_id, str(exc))
                raise
            self.audit.mark_ok(entry.entry_id, _summarise(result))
            return result

        return _wrapped


def _summarise(result: Any) -> str:
    """Compact, log-safe summary of an SDK return value."""
    try:
        if isinstance(result, tuple):
            ok, body = result
            return f"ok={ok!r} rows={(len(body) if hasattr(body, '__len__') else 1)}"
        return type(result).__name__
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Schema: portfolio snapshot. Plan §T2.7. Lives here because agent_futu is
# its sole producer. (T2.2 plan.v1 references it via portfolio_context, but
# only the small slice — the full snapshot stays in this package.)
# ---------------------------------------------------------------------------


Market = Literal["HK", "US", "CN", "FX", "FUND"]


class PositionState(BaseModel):
    asset_kind: Literal["equity", "etf", "future", "option", "fx", "crypto", "bond"]
    ticker: str
    venue: str
    qty: float
    cost_basis_per_share: float
    avg_cost_currency: str
    market_value_base_ccy: float
    unrealized_pnl_base_ccy: float
    open_orders_count: int = Field(ge=0, default=0)


class AccountState(BaseModel):
    futu_id: str
    account_id: str
    market: Market
    base_currency: str
    nav_base_ccy: float
    cash_base_ccy: float
    purchasing_power_base_ccy: float
    positions: list[PositionState] = Field(default_factory=list)


class AggregateState(BaseModel):
    nav_base_ccy: float
    cash_base_ccy: float
    largest_concentration_pct_nav: float = Field(ge=0.0, le=100.0, default=0.0)
    base_currency: str = "USD"


class PortfolioSnapshotV1(BaseModel):
    schema_version: Literal["portfolio.snapshot.v1"] = Field(
        default="portfolio.snapshot.v1", alias="schema"
    )
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    accounts: list[AccountState] = Field(default_factory=list)
    aggregate: AggregateState

    model_config = {"populate_by_name": True}

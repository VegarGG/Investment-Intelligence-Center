"""FutuQuoteClient — read-only OpenQuoteContext wrapper (P4.3).

Mirrors the construction of ``FutuReadOnlyClient`` (trading context):
an allow-list + ``__getattr__`` deny-by-default surface. Defense in
depth even though OpenQuoteContext has no order-placement methods —
the pattern guards against an SDK upgrade silently exposing one.

Allowed methods:
  - get_market_snapshot
  - get_cur_kline
  - get_order_book
  - subscribe
  - unsubscribe
  - get_global_state
  - get_history_kl_quota

Real backend swap is identical to RealOpenD (P4.1): lazy `futu` import,
gated by env (``FUTU_OPEND_HOST`` / port).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)

QUOTE_ALLOWED_METHODS: frozenset[str] = frozenset(
    {
        "get_market_snapshot",
        "get_cur_kline",
        "get_order_book",
        "subscribe",
        "unsubscribe",
        "get_global_state",
        "get_history_kl_quota",
    }
)


class FutuQuoteForbiddenError(Exception):
    """Raised when a non-allowlisted method is called on the wrapper."""


class _QuoteCtxLike(Protocol):
    def get_market_snapshot(self, code_list: list[str]) -> Any: ...
    def get_cur_kline(self, code: str, num: int, ktype: str) -> Any: ...
    def get_order_book(self, code: str, num: int = 10) -> Any: ...
    def subscribe(self, code_list: list[str], subtype_list: list[str]) -> Any: ...
    def unsubscribe(self, code_list: list[str], subtype_list: list[str]) -> Any: ...
    def get_global_state(self) -> Any: ...
    def get_history_kl_quota(self) -> Any: ...


@dataclass(slots=True)
class FutuQuoteClient:
    """Read-only wrapper around a real-or-fake OpenQuoteContext."""

    ctx: _QuoteCtxLike

    def __getattr__(self, name: str) -> Any:
        if name not in QUOTE_ALLOWED_METHODS:
            raise FutuQuoteForbiddenError(
                f"FutuQuoteClient has no attribute {name!r}; "
                f"allowed: {sorted(QUOTE_ALLOWED_METHODS)}"
            )
        underlying = getattr(self.ctx, name, None)
        if underlying is None:
            raise FutuQuoteForbiddenError(
                f"underlying quote ctx does not expose {name!r}"
            )
        return underlying


class FakeQuoteCtx:
    """Deterministic test fixture mirroring the OpenQuoteContext surface."""

    def __init__(self, snapshots: dict[str, dict[str, Any]] | None = None) -> None:
        self.snapshots = snapshots or {}
        self.subs: set[str] = set()

    def get_market_snapshot(self, code_list: list[str]) -> tuple[int, list[dict[str, Any]]]:
        rows = []
        for code in code_list:
            snap = self.snapshots.get(code, {})
            rows.append({"code": code, "last_price": snap.get("last", 0.0), "volume": snap.get("vol", 0)})
        return 0, rows

    def get_cur_kline(self, code: str, num: int, ktype: str) -> tuple[int, list[dict[str, Any]]]:
        return 0, []

    def get_order_book(self, code: str, num: int = 10) -> tuple[int, dict[str, Any]]:
        return 0, {"code": code, "bids": [], "asks": []}

    def subscribe(self, code_list: list[str], subtype_list: list[str]) -> tuple[int, str]:
        for c in code_list:
            self.subs.add(c)
        return 0, "ok"

    def unsubscribe(self, code_list: list[str], subtype_list: list[str]) -> tuple[int, str]:
        for c in code_list:
            self.subs.discard(c)
        return 0, "ok"

    def get_global_state(self) -> tuple[int, dict[str, Any]]:
        return 0, {"server_ver": "fake", "market_open": True}

    def get_history_kl_quota(self) -> tuple[int, dict[str, Any]]:
        return 0, {"used": 0, "remain": 1000}


class RealQuoteCtx:
    """Lazy adapter around `futu.OpenQuoteContext`. Same pattern as
    `RealOpenD` — the futu-api dep is not required at import time."""

    __slots__ = ("_host", "_port", "_ctx")

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._host = host or os.environ.get("FUTU_OPEND_HOST", "127.0.0.1")
        self._port = int(port or int(os.environ.get("FUTU_OPEND_PORT", "11111")))
        self._ctx: Any = None

    def _real_ctx(self) -> Any:
        if self._ctx is not None:
            return self._ctx
        try:
            from futu import OpenQuoteContext  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("futu-api not installed") from exc
        self._ctx = OpenQuoteContext(host=self._host, port=self._port)
        return self._ctx

    def get_market_snapshot(self, code_list: list[str]) -> Any:
        return self._real_ctx().get_market_snapshot(code_list=code_list)

    def get_cur_kline(self, code: str, num: int, ktype: str) -> Any:
        return self._real_ctx().get_cur_kline(code=code, num=num, ktype=ktype)

    def get_order_book(self, code: str, num: int = 10) -> Any:
        return self._real_ctx().get_order_book(code=code, num=num)

    def subscribe(self, code_list: list[str], subtype_list: list[str]) -> Any:
        return self._real_ctx().subscribe(code_list=code_list, subtype_list=subtype_list)

    def unsubscribe(self, code_list: list[str], subtype_list: list[str]) -> Any:
        return self._real_ctx().unsubscribe(code_list=code_list, subtype_list=subtype_list)

    def get_global_state(self) -> Any:
        return self._real_ctx().get_global_state()

    def get_history_kl_quota(self) -> Any:
        return self._real_ctx().get_history_kl_quota()


def make_quote_client_from_env() -> FutuQuoteClient:
    """Build a FutuQuoteClient from env: real backend, or fake when
    ``FUTU_QUOTE_BACKEND=fake``."""
    backend = os.environ.get("FUTU_QUOTE_BACKEND", "real").lower()
    if backend == "fake":
        return FutuQuoteClient(ctx=FakeQuoteCtx())
    return FutuQuoteClient(ctx=RealQuoteCtx())

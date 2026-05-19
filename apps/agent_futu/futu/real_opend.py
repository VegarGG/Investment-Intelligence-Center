"""Real OpenD adapter (P4.1 / Phase B3.3b).

Wraps ``futu.OpenSecTradeContext`` so it satisfies the same ``_OpenDLike``
Protocol as the test fixture. Configuration is per-Futu-ID:

  - ``FUTU_OPEND_HOST`` (default ``127.0.0.1``)
  - ``FUTU_OPEND_PORT`` (default ``11111``)
  - ``FUTU_OPEND_TIMEOUT`` (default ``5`` seconds)
  - ``FUTU_OPEND_TLS_CERT`` (optional PEM path)

The real ``OpenSecTradeContext`` is constructed lazily so unit tests
importing this module do not require the ``futu-api`` package installed.

Phase B3.3b safety:
  - ``unlock_trade`` is permanently disabled at the wrapper level
    (``FutuReadOnlyClient`` raises on the literal name).
  - ``lake.futu_audit`` Postgres trigger + REVOKE UPDATE/DELETE on the
    table (migration 0009, P4.1 prerequisite) provides DB-side immutability.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass(slots=True)
class RealOpenDConfig:
    host: str = "127.0.0.1"
    port: int = 11111
    timeout_s: int = 5
    tls_cert: str | None = None

    @classmethod
    def from_env(cls) -> "RealOpenDConfig":
        return cls(
            host=os.environ.get("FUTU_OPEND_HOST", "127.0.0.1"),
            port=int(os.environ.get("FUTU_OPEND_PORT", "11111")),
            timeout_s=int(os.environ.get("FUTU_OPEND_TIMEOUT", "5")),
            tls_cert=os.environ.get("FUTU_OPEND_TLS_CERT") or None,
        )


class RealOpenD:
    """Adapter that exposes the same surface as FakeOpenD but talks to a
    real OpenD instance via futu-api.

    Lazy SDK import keeps unit tests that don't need OpenD-free of the
    futu-api dependency.
    """

    __slots__ = ("_cfg", "_trd_ctx")

    def __init__(self, config: RealOpenDConfig | None = None) -> None:
        self._cfg = config or RealOpenDConfig.from_env()
        self._trd_ctx: Any = None

    def _ctx(self) -> Any:
        if self._trd_ctx is not None:
            return self._trd_ctx
        try:
            from futu import OpenSecTradeContext  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "futu-api not installed; install with `pip install futu-api`"
            ) from exc
        kwargs: dict[str, Any] = {"host": self._cfg.host, "port": self._cfg.port}
        if self._cfg.tls_cert:
            kwargs["is_encrypt"] = True
        ctx = OpenSecTradeContext(**kwargs)
        self._trd_ctx = ctx
        log.info(
            "real_opend connected host=%s port=%s tls=%s",
            self._cfg.host,
            self._cfg.port,
            bool(self._cfg.tls_cert),
        )
        return ctx

    # ---- _OpenDLike protocol forwards ---------------------------------------
    def get_acc_list(self) -> Any:
        return self._ctx().get_acc_list()

    def accinfo_query(self, acc_id: str) -> Any:
        return self._ctx().accinfo_query(acc_id=acc_id)

    def position_list_query(self, acc_id: str) -> Any:
        return self._ctx().position_list_query(acc_id=acc_id)

    def order_list_query(self, acc_id: str) -> Any:
        return self._ctx().order_list_query(acc_id=acc_id)

    def history_order_list_query(self, acc_id: str, **kw: Any) -> Any:
        return self._ctx().history_order_list_query(acc_id=acc_id, **kw)

    def history_deal_list_query(self, acc_id: str, **kw: Any) -> Any:
        return self._ctx().history_deal_list_query(acc_id=acc_id, **kw)

    def get_market_state(self, codes: list[str]) -> Any:
        return self._ctx().get_market_state(code_list=codes)

    def close(self) -> None:
        if self._trd_ctx is not None:
            try:
                self._trd_ctx.close()
            except Exception as exc:  # noqa: BLE001
                log.warning("real_opend close failed: %s", exc)
            self._trd_ctx = None

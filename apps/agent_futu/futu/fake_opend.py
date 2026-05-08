"""Deterministic FakeOpenD fixture (v2.5 B3.3a).

Mirrors the shape of the real `futu.OpenSecTradeContext` for the methods
``FutuReadOnlyClient`` relies on. Two Futu IDs, five positions each, all
deterministic — `pytest --randomly` cannot perturb the data.

NOT a security boundary. The wrapper is the security boundary. This
fixture is purely a test convenience.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# OpenAPI's idiomatic return shape is `(ret, data)` where `ret` is an int
# (0 = OK) and `data` is a list-of-dict payload. We mirror that shape.
RET_OK = 0


@dataclass(slots=True)
class FakeOpenD:
    futu_id: str  # the unhashed login id; FakeOpenD knows it for fixture realism
    accounts: list[dict[str, Any]] = field(default_factory=list)
    positions_by_account: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def get_acc_list(self) -> tuple[int, list[dict[str, Any]]]:
        return RET_OK, list(self.accounts)

    def accinfo_query(self, acc_id: str) -> tuple[int, list[dict[str, Any]]]:
        for acc in self.accounts:
            if acc["acc_id"] == acc_id:
                return RET_OK, [
                    {
                        "acc_id": acc_id,
                        "currency": acc.get("base_currency", "USD"),
                        "total_assets": acc.get("nav", 0.0),
                        "cash": acc.get("cash", 0.0),
                        "power": acc.get("purchasing_power", 0.0),
                    }
                ]
        return -1, []

    def position_list_query(self, acc_id: str) -> tuple[int, list[dict[str, Any]]]:
        return RET_OK, list(self.positions_by_account.get(acc_id, []))

    def order_list_query(self, acc_id: str) -> tuple[int, list[dict[str, Any]]]:
        # Empty open-order list — Phase 2 fixtures will populate.
        _ = acc_id
        return RET_OK, []

    def history_order_list_query(self, acc_id: str, **_: Any) -> tuple[int, list[dict[str, Any]]]:
        _ = acc_id
        return RET_OK, []

    def history_deal_list_query(self, acc_id: str, **_: Any) -> tuple[int, list[dict[str, Any]]]:
        _ = acc_id
        return RET_OK, []

    def get_market_state(self, codes: list[str]) -> tuple[int, list[dict[str, Any]]]:
        return RET_OK, [{"code": c, "market_state": "TRADE"} for c in codes]


def make_fake_openD_pair() -> tuple[FakeOpenD, FakeOpenD]:
    """Return two FakeOpenDs with deterministic positions for tests."""

    a = FakeOpenD(
        futu_id="ZW-PRIMARY",
        accounts=[
            {
                "acc_id": "acc-001",
                "base_currency": "USD",
                "nav": 100_000.0,
                "cash": 25_000.0,
                "purchasing_power": 50_000.0,
            }
        ],
        positions_by_account={
            "acc-001": [
                {"code": "US.AAPL", "qty": 100, "cost_price": 150.0, "market_val": 22_000.0, "pl_val": 7_000.0},
                {"code": "US.MSFT", "qty": 50, "cost_price": 300.0, "market_val": 22_500.0, "pl_val": 7_500.0},
                {"code": "US.SPY", "qty": 20, "cost_price": 400.0, "market_val": 9_000.0, "pl_val": 1_000.0},
                {"code": "US.GLD", "qty": 40, "cost_price": 200.0, "market_val": 9_200.0, "pl_val": 1_200.0},
                {"code": "US.TLT", "qty": 100, "cost_price": 90.0, "market_val": 9_300.0, "pl_val": 300.0},
            ]
        },
    )
    b = FakeOpenD(
        futu_id="ZW-FAMILY",
        accounts=[
            {
                "acc_id": "acc-100",
                "base_currency": "HKD",
                "nav": 500_000.0,
                "cash": 200_000.0,
                "purchasing_power": 300_000.0,
            }
        ],
        positions_by_account={
            "acc-100": [
                {"code": "HK.00700", "qty": 200, "cost_price": 350.0, "market_val": 80_000.0, "pl_val": 10_000.0},
                {"code": "HK.09988", "qty": 1000, "cost_price": 80.0, "market_val": 90_000.0, "pl_val": 10_000.0},
                {"code": "HK.02800", "qty": 5000, "cost_price": 21.0, "market_val": 110_000.0, "pl_val": 5_000.0},
                {"code": "HK.03690", "qty": 500, "cost_price": 100.0, "market_val": 55_000.0, "pl_val": 5_000.0},
                {"code": "HK.01211", "qty": 200, "cost_price": 220.0, "market_val": 47_000.0, "pl_val": 3_000.0},
            ]
        },
    )
    return a, b

"""Aggregate read-only snapshots across N OpenD endpoints (v2.5 B3.3a)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime

from .readonly_client import (
    AccountState,
    AggregateState,
    FutuReadOnlyClient,
    PortfolioSnapshotV1,
    PositionState,
)


def hash_futu_id(futu_id: str) -> str:
    """Hash a raw Futu ID. Stable, lossless wrt collision risk."""
    return "fid_" + hashlib.sha256(futu_id.encode()).hexdigest()[:16]


def aggregate_snapshot(clients: Sequence[FutuReadOnlyClient]) -> PortfolioSnapshotV1:
    """Build a `portfolio.snapshot.v1` from N read-only clients."""

    accounts: list[AccountState] = []
    total_nav = 0.0
    total_cash = 0.0

    for client in clients:
        ret, acc_list = client.get_acc_list()
        if ret != 0:
            continue
        for acc in acc_list:
            acc_id = acc["acc_id"]
            base_ccy = acc.get("base_currency", "USD")
            ret_pos, pos_list = client.position_list_query(acc_id)
            positions: list[PositionState] = []
            if ret_pos == 0:
                for p in pos_list:
                    code: str = p["code"]
                    venue, ticker = _parse_code(code)
                    positions.append(
                        PositionState(
                            asset_kind="equity",
                            ticker=ticker,
                            venue=venue,
                            qty=float(p["qty"]),
                            cost_basis_per_share=float(p.get("cost_price", 0.0)),
                            avg_cost_currency=base_ccy,
                            market_value_base_ccy=float(p.get("market_val", 0.0)),
                            unrealized_pnl_base_ccy=float(p.get("pl_val", 0.0)),
                            open_orders_count=0,
                        )
                    )
            account = AccountState(
                futu_id=client.futu_id_hash,
                account_id=acc_id,
                market=_market_from_positions(positions, base_ccy),
                base_currency=base_ccy,
                nav_base_ccy=float(acc.get("nav", 0.0)),
                cash_base_ccy=float(acc.get("cash", 0.0)),
                purchasing_power_base_ccy=float(acc.get("purchasing_power", 0.0)),
                positions=positions,
            )
            accounts.append(account)
            total_nav += account.nav_base_ccy
            total_cash += account.cash_base_ccy

    largest_concentration = _largest_concentration_pct(accounts, total_nav)
    return PortfolioSnapshotV1(
        snapshot_at=datetime.now(UTC),
        accounts=accounts,
        aggregate=AggregateState(
            nav_base_ccy=total_nav,
            cash_base_ccy=total_cash,
            largest_concentration_pct_nav=largest_concentration,
            base_currency="USD",
        ),
    )


def _parse_code(code: str) -> tuple[str, str]:
    if "." in code:
        venue, ticker = code.split(".", 1)
        return venue.upper(), ticker
    return "UNKNOWN", code


def _market_from_positions(
    positions: list[PositionState], base_ccy: str
) -> str:
    if not positions:
        return "FUND" if base_ccy == "USD" else "FX"
    venues = {p.venue for p in positions}
    if "HK" in venues:
        return "HK"
    if any(v in {"NASDAQ", "NYSE", "ARCA", "US"} for v in venues):
        return "US"
    return "US"


def _largest_concentration_pct(accounts: list[AccountState], total_nav: float) -> float:
    if total_nav <= 0:
        return 0.0
    largest = 0.0
    for acc in accounts:
        for pos in acc.positions:
            pct = abs(pos.market_value_base_ccy) / total_nav * 100.0
            if pct > largest:
                largest = pct
    return min(largest, 100.0)

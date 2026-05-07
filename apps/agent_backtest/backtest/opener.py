"""Advice → Position (workflow 14 §5.1).

Idempotent on advice.id — replays of the same advice never open a duplicate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from schema import AdviceV1

from .slippage import fill_price
from .types import Position


class PositionStore(Protocol):
    async def upsert(self, position: Position) -> bool: ...

    async def get(self, advice_id: str) -> Position | None: ...

    async def open_positions(self) -> list[Position]: ...

    async def closed_positions(self) -> list[Position]: ...


class InMemoryPositionStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Position] = {}

    async def upsert(self, position: Position) -> bool:
        new = position.advice_id not in self._by_id
        self._by_id[position.advice_id] = position
        return new

    async def get(self, advice_id: str) -> Position | None:
        return self._by_id.get(advice_id)

    async def open_positions(self) -> list[Position]:
        return [p for p in self._by_id.values() if p.state == "open"]

    async def closed_positions(self) -> list[Position]:
        return [p for p in self._by_id.values() if p.state == "closed"]


async def open_position(
    advice: AdviceV1,
    store: PositionStore,
    *,
    median_dollar_volume_5d: float = 1_000_000,
    realized_vol_20d_pct: float = 20.0,
) -> Position:
    existing = await store.get(advice.id)
    if existing is not None:
        return existing
    if advice.direction == "flat":
        raise ValueError("backtester does not open positions for direction=flat")
    px = fill_price(
        entry_band=advice.entry_band,
        direction=advice.direction,
        venue=advice.asset.venue,
        size_usd=advice.sizing_hint_pct_nav * 1_000_000 / 100.0,
        median_dollar_volume_5d=median_dollar_volume_5d,
        realized_vol_20d_pct=realized_vol_20d_pct,
    )
    pos = Position(
        advice_id=advice.id,
        agent=advice.agent,
        ticker=advice.asset.ticker,
        venue=advice.asset.venue,
        direction=advice.direction,
        entry_band=advice.entry_band,
        target_band=advice.target_band,
        stop_loss=advice.stop_loss,
        expires_at=advice.expires_at,
        opened_at=datetime.now(UTC),
        fill_px=px,
    )
    await store.upsert(pos)
    return pos

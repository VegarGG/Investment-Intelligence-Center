"""Per-tick MTM batcher (workflow 14 §5.2).

Pulls all open positions once per tick, dedupes price queries by symbol,
parallel-fetches via the Pricer, then runs exit detection + closes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from ..exits import check_exit, realize_pnl
from ..opener import PositionStore
from ..types import Position
from .pricer import Pricer


async def tick(
    store: PositionStore,
    pricer: Pricer,
    *,
    asof: datetime,
    on_close: Callable[[Position], Awaitable[None]] | None = None,
) -> int:
    """Run one MTM tick. Returns the number of positions closed this tick."""
    open_positions = await store.open_positions()
    tickers = {p.ticker for p in open_positions}
    marks = await asyncio.gather(*[pricer.latest(t, asof=asof) for t in tickers])
    px_by_ticker = {t: m.price for t, m in zip(tickers, marks, strict=False) if m is not None}
    closed = 0
    for pos in open_positions:
        px = px_by_ticker.get(pos.ticker)
        if px is None:
            continue
        pos.marks.append((asof, px))
        exited, reason, exit_px = check_exit(pos, px, asof=asof)
        if exited:
            pos.state = "closed"
            pos.closed_at = asof
            pos.exit_px = exit_px
            pos.exit_reason = reason
            pos.pnl_usd, pos.pnl_r = realize_pnl(pos, exit_px)
            await store.upsert(pos)
            closed += 1
            if on_close:
                await on_close(pos)
    return closed

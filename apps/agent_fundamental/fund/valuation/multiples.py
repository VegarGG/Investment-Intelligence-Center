"""Peer multiples comparison (workflow 11 §5.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MultiplesSummary:
    pe: float | None
    pe_peer_median: float | None
    pe_premium_pct: float | None
    ev_ebitda: float | None
    ev_ebitda_peer_median: float | None
    fcf_yield: float | None
    fcf_yield_peer_median: float | None


def peer_multiples_summary(
    target: Mapping[str, float | None],
    peers: Mapping[str, Mapping[str, float | None]],
) -> MultiplesSummary:
    """Compare target multiples to the median of `peers`. Mismatched units
    are caller's responsibility (workflow 11 §9 currency note)."""

    def _median(key: str) -> float | None:
        vals = [v[key] for v in peers.values() if v.get(key) is not None]
        if not vals:
            return None
        vals_sorted = sorted(v for v in vals if v is not None)
        mid = len(vals_sorted) // 2
        if len(vals_sorted) % 2:
            return vals_sorted[mid]
        return (vals_sorted[mid - 1] + vals_sorted[mid]) / 2

    pe = target.get("pe")
    pe_med = _median("pe")
    pe_premium = (pe / pe_med - 1.0) if (pe is not None and pe_med) else None

    return MultiplesSummary(
        pe=pe,
        pe_peer_median=pe_med,
        pe_premium_pct=pe_premium,
        ev_ebitda=target.get("ev_ebitda"),
        ev_ebitda_peer_median=_median("ev_ebitda"),
        fcf_yield=target.get("fcf_yield"),
        fcf_yield_peer_median=_median("fcf_yield"),
    )

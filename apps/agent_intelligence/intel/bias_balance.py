"""compute_bias_balance + the §5.10 hard-rule helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from schema import BiasBalance

from .types import Event, SourceCfg

DOMINANCE_THRESHOLD = 0.55


def compute(events: Iterable[Event], source_weights: dict[str, float]) -> BiasBalance:
    by_region: defaultdict[str, float] = defaultdict(float)
    by_lean: defaultdict[str, float] = defaultdict(float)
    total = 0.0
    for ev in events:
        w = source_weights.get(ev.source_id, 1.0)
        by_region[ev.source_region] += w
        by_lean[ev.source_lean] += w
        total += w
    if total == 0.0:
        return BiasBalance()
    return BiasBalance(
        by_region={k: v / total for k, v in by_region.items()},
        by_lean={k: v / total for k, v in by_lean.items()},
    )


def dominant_region(balance: BiasBalance, threshold: float = DOMINANCE_THRESHOLD) -> str | None:
    """Return the region whose share exceeds the threshold, else None."""
    over = [(r, s) for r, s in balance.by_region.items() if s > threshold]
    if not over:
        return None
    return max(over, key=lambda kv: kv[1])[0]


def weights_from(sources: Iterable[SourceCfg]) -> dict[str, float]:
    return {s.id: s.region_weight for s in sources}

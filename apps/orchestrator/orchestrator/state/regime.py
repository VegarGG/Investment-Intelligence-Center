"""Extract macro_regime from intel.digest.v1 (workflow 06 §6.2 step n_update_kv)."""

from __future__ import annotations

from typing import Any

VALID_REGIMES = (
    "rate_cut",
    "risk_on",
    "risk_off",
    "stagflation",
    "recession",
    "crisis",
    "unknown",
)


def regime_from_digest(digest: dict[str, Any] | Any) -> str:
    """Pull macro_regime out of a digest payload, falling back to 'unknown'."""
    if hasattr(digest, "macro_regime"):
        value = digest.macro_regime
    elif isinstance(digest, dict):
        value = digest.get("macro_regime", "unknown")
    else:
        value = "unknown"
    return str(value) if value in VALID_REGIMES else "unknown"

"""Persona domain types (workflow 13 §2.2).

v2.5 T1.1d — `BandRules` is the persona-specific recipe for deriving
`(direction, entry_band, target_band, stop_loss)` from the live mark and
the digest's `macro_regime`. Defaults are conservative (`flat`, single px)
so chaos drills with `band_rules=None` still produce schema-valid advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CanonicalTrade:
    era: str
    asset: str
    action: str
    lesson: str


@dataclass(frozen=True, slots=True)
class MemoryScope:
    retain_days: int = 365
    bias_categories: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BandRules:
    """Persona-specific recipe for translating a live mark into bands.

    Fields
    ------
    direction_default : Literal["long","short","flat"]
        The persona's default directional bias when the LLM thesis is
        non-committal.
    target_pct_over_mark : float
        Distance from mark to target as a fraction (e.g. 0.25 = +25 % for
        `long`, -25 % for `short`).
    stop_pct_under_mark : float
        Distance from mark to stop as a fraction (e.g. 0.10 = -10 % for
        `long`, +10 % for `short`).
    entry_band_pct : float
        Half-width of the entry band around the mark (default 0.005 = ±0.5 %).
    horizon_days : int
        Persona-preferred horizon. Falls back to advice default when missing.
    confidence_floor : float
        Minimum confidence the persona will emit; LLM thesis text can lift
        but not lower this.
    macro_regime_modulation : bool
        When True, target_pct_over_mark is multiplied by the digest's
        macro_regime: bull → 1.5, bear → 0.5, neutral/unknown → 1.0. Soros
        and Druckenmiller use this; Buffett does not.
    """

    direction_default: str = "flat"
    target_pct_over_mark: float = 0.0
    stop_pct_under_mark: float = 0.0
    entry_band_pct: float = 0.005
    horizon_days: int = 180
    confidence_floor: float = 0.5
    macro_regime_modulation: bool = False


@dataclass(frozen=True, slots=True)
class PersonaSpec:
    slug: str
    display_name: str
    priors: tuple[str, ...]
    canonical_trades: tuple[CanonicalTrade, ...]
    universe_weights: dict[str, float]
    prompt_template_ref: str
    memory_scope: MemoryScope
    guardrails: tuple[str, ...]
    disclaimer: str
    band_rules: BandRules | None = None


@dataclass(slots=True)
class MemoryEntry:
    """One row in the persona's ChromaDB collection (workflow 13 §2.3)."""

    doc_id: str
    text: str
    kind: str  # "decision" | "reasoning" | "lesson"
    similarity: float = 0.0
    pnl_r: float | None = None
    days_old: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

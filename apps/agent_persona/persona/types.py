"""Persona domain types (workflow 13 §2.2)."""

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

"""Persona YAML loader + validator (workflow 13 §5.1).

Fail loud at boot — a malformed persona file should crash the container,
not silently disable a desk member.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .types import BandRules, CanonicalTrade, MemoryScope, PersonaSpec


def load(path: str | Path) -> PersonaSpec:
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: persona file must be a mapping")
    try:
        return _to_spec(raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{path}: invalid persona spec — {exc}") from exc


def load_dir(path: str | Path) -> dict[str, PersonaSpec]:
    out: dict[str, PersonaSpec] = {}
    for f in sorted(Path(path).glob("*.yaml")):
        spec = load(f)
        if spec.slug in out:
            raise ValueError(f"duplicate persona slug: {spec.slug}")
        out[spec.slug] = spec
    return out


def _to_spec(row: dict[str, Any]) -> PersonaSpec:
    if "slug" not in row or "display_name" not in row:
        raise KeyError("persona spec requires 'slug' and 'display_name'")
    if "disclaimer" not in row:
        raise KeyError("persona spec requires 'disclaimer'")
    return PersonaSpec(
        slug=str(row["slug"]),
        display_name=str(row["display_name"]),
        priors=tuple(str(p) for p in row.get("priors", [])),
        canonical_trades=tuple(
            CanonicalTrade(
                era=str(c.get("era", "")),
                asset=str(c.get("asset", "")),
                action=str(c.get("action", "")),
                lesson=str(c.get("lesson", "")),
            )
            for c in row.get("canonical_trades", [])
        ),
        universe_weights={k: float(v) for k, v in row.get("universe_weights", {}).items()},
        prompt_template_ref=str(row.get("prompt_template_ref", "persona.daily.base@1.0.0")),
        memory_scope=MemoryScope(
            retain_days=int(row.get("memory_scope", {}).get("retain_days", 365)),
            bias_categories=tuple(
                str(c) for c in row.get("memory_scope", {}).get("bias_categories", [])
            ),
        ),
        guardrails=tuple(str(g) for g in row.get("guardrails", [])),
        disclaimer=str(row["disclaimer"]),
        band_rules=_band_rules(row.get("band_rules")),
    )


def _band_rules(raw: Any) -> BandRules | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"band_rules must be a mapping, got {type(raw).__name__}")
    direction = str(raw.get("direction_default", "flat")).strip().lower()
    if direction not in {"long", "short", "flat"}:
        raise ValueError(f"band_rules.direction_default must be long|short|flat, got {direction!r}")
    return BandRules(
        direction_default=direction,
        target_pct_over_mark=float(raw.get("target_pct_over_mark", 0.0)),
        stop_pct_under_mark=float(raw.get("stop_pct_under_mark", 0.0)),
        entry_band_pct=float(raw.get("entry_band_pct", 0.005)),
        horizon_days=int(raw.get("horizon_days", 180)),
        confidence_floor=float(raw.get("confidence_floor", 0.5)),
        macro_regime_modulation=bool(raw.get("macro_regime_modulation", False)),
    )

"""Single source of truth for personas (v2.5 T0.2).

Loads `docs/prompts/persona/*.yaml` once and exposes a snapshot to every
DAG. `morning_brief.py`, `app.py:_bootstrap`, and the upcoming trading-room
DAG (T2.x) all consume the same list — three-place drift can no longer
desynchronise the slug list, the URL map, and the YAML directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

@dataclass(frozen=True, slots=True)
class PersonaSpec:
    slug: str
    display_name: str


def _default_dir() -> Path:
    """Compute the default persona-yaml dir lazily.

    In the source tree the file lives at
    ``<repo>/apps/orchestrator/orchestrator/plan/personas.py`` so
    ``parents[4]`` is the repo root. In a container where the source is
    mounted at ``/app/orchestrator/...`` the path is shorter; doing the
    arithmetic at import time crashes. Make it lazy and let
    ``IIC_PERSONA_DIR`` override in deployments where the layout differs.
    """
    parents = Path(__file__).resolve().parents
    if len(parents) >= 5:
        return parents[4] / "docs" / "prompts" / "persona"
    # Fallback for container layouts: assume docs/ sits next to the
    # outermost dir on sys.path, e.g. /app/docs/prompts/persona.
    return Path("/app") / "docs" / "prompts" / "persona"


# Kept as a lazily-initialised property so import never crashes when
# parents[4] is unreachable. Use _resolve_dir() at call sites.
DEFAULT_DIR = _default_dir() if len(Path(__file__).resolve().parents) >= 5 else None  # type: ignore[assignment]


def _resolve_dir() -> Path:
    raw = os.environ.get("IIC_PERSONA_DIR")
    if raw:
        return Path(raw)
    return _default_dir()


def list_personas(force_reload: bool = False) -> list[PersonaSpec]:
    """Return personas declared by `docs/prompts/persona/*.yaml`.

    Sorted by slug for deterministic fan-out (so DAGs are stable across
    restarts and the dashboard's leaderboard order doesn't churn).
    """

    if force_reload:
        _load_specs.cache_clear()
    return _load_specs(str(_resolve_dir()))


@lru_cache(maxsize=4)
def _load_specs(dir_path: str) -> list[PersonaSpec]:
    p = Path(dir_path)
    if not p.exists():
        return []
    out: list[PersonaSpec] = []
    seen: set[str] = set()
    for f in sorted(p.glob("*.yaml")):
        raw = yaml.safe_load(f.read_text()) or {}
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or f.stem).strip()
        if not slug:
            continue
        if slug in seen:
            raise ValueError(f"duplicate persona slug across YAML files: {slug}")
        seen.add(slug)
        display = str(raw.get("display_name", slug.title()))
        out.append(PersonaSpec(slug=slug, display_name=display))
    return sorted(out, key=lambda s: s.slug)


def list_persona_slugs(force_reload: bool = False) -> tuple[str, ...]:
    return tuple(s.slug for s in list_personas(force_reload=force_reload))

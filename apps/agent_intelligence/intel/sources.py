"""sources.yaml loader + lookup (workflow 10 §2.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .types import SourceCfg


def load_sources(path: str | Path) -> list[SourceCfg]:
    """Parse `sources.yaml` into SourceCfg list. Fail loud on bad rows so a
    typo doesn't silently strip half the manifest."""
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a list of sources, got {type(raw).__name__}")
    out: list[SourceCfg] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"{path}[{i}]: expected mapping, got {type(row).__name__}")
        try:
            out.append(_to_cfg(row))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}[{i}] ({row.get('id', '?')}): {exc}") from exc
    return out


def _to_cfg(row: dict[str, Any]) -> SourceCfg:
    return SourceCfg(
        id=str(row["id"]),
        region=str(row["region"]),
        lean=str(row["lean"]),
        region_weight=float(row["region_weight"]),
        language=str(row.get("language", "en")),
        url=row.get("url"),
        channel=row.get("channel"),
        rate_limit=row.get("rate_limit"),
    )


def by_id(sources: list[SourceCfg]) -> dict[str, SourceCfg]:
    out: dict[str, SourceCfg] = {}
    for s in sources:
        if s.id in out:
            raise ValueError(f"duplicate source id: {s.id}")
        out[s.id] = s
    return out

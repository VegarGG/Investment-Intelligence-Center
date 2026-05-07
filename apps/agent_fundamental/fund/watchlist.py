"""Watchlist loader (workflow 11 §2.2)."""

from __future__ import annotations

from pathlib import Path

import yaml

from .types import WatchlistEntry


def load(path: str | Path) -> list[WatchlistEntry]:
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a list of watchlist entries")
    out: list[WatchlistEntry] = []
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"{path}[{i}]: expected mapping")
        try:
            out.append(
                WatchlistEntry(
                    ticker=str(row["ticker"]),
                    venue=str(row["venue"]),
                    sector=str(row["sector"]),
                    thesis_tag=str(row.get("thesis_tag", "")),
                    peers=tuple(str(p) for p in row.get("peers", [])),
                )
            )
        except KeyError as exc:
            raise ValueError(f"{path}[{i}]: missing key {exc}") from exc
    return out

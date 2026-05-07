"""Macro release protocol. Production wires FRED / ECB / PBoC / etc."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MacroRelease:
    source: str
    series: str
    released_at: datetime
    value: float
    note: str = ""


class MacroSource(Protocol):
    async def fetch(self, asof: datetime) -> list[MacroRelease]: ...


class InMemoryMacroSource:
    """Replay a fixed list — useful for tests and synth fixtures."""

    def __init__(self, releases: Iterable[MacroRelease]) -> None:
        self._releases = list(releases)

    async def fetch(self, asof: datetime) -> list[MacroRelease]:
        return [r for r in self._releases if r.released_at <= asof]

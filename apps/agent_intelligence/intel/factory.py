"""Deterministic IntelPipeline factory (v2.5 T1.3).

`build_pipeline(config)` is the single entry point that wires the
crawler, dedupe gates, macro source, and event store into an
`IntelPipeline`. Production binds it from `_startup` when
`INTEL_AUTOSTART=1`; tests bind it explicitly via `set_pipeline()`.

The default factory uses the in-memory implementations of every
collaborator. Production deployments replace them by environment:

- `INTEL_HASH_STORE_BACKEND=redis` — switch the hash gate to Redis.
- `INTEL_EVENT_STORE_BACKEND=postgres` — switch the event store to Postgres.
- `INTEL_CRAWLER_BACKEND=rss` — start the live RSS crawler.

Each backend's import is lazy so the in-memory smoke tests run without
needing the real client libs installed.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from . import sources as sources_mod
from .crawler.protocol import CrawlerProtocol, InMemoryCrawler
from .dedupe.hash_gate import HashGate, HashStore, InMemoryHashStore
from .dedupe.semantic_gate import (
    InMemorySemanticIndex,
    SemanticGate,
    SemanticIndex,
    hash_embed,
)
from .macro import InMemoryMacroSource, MacroSource
from .persistence import EventStore, InMemoryEventStore
from .pipeline import IntelPipeline
from .types import SourceCfg

if TYPE_CHECKING:  # noqa: F401
    pass


@dataclass(slots=True)
class IntelConfig:
    """Resolved configuration for `build_pipeline`. Built from env or by tests."""

    sources: list[SourceCfg] = field(default_factory=list)
    crawler: CrawlerProtocol | None = None
    hash_store: HashStore | None = None
    semantic_index: SemanticIndex | None = None
    macro: MacroSource | None = None
    event_store: EventStore | None = None
    built_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_env(cls) -> "IntelConfig":
        """Build an IntelConfig from process env. Missing fields → in-memory defaults."""

        srcs: list[SourceCfg] = []
        sources_path = os.environ.get("INTEL_SOURCES_PATH")
        if sources_path and Path(sources_path).exists():
            srcs = sources_mod.load_sources(sources_path)
        return cls(sources=srcs)


def build_pipeline(
    config: IntelConfig | None = None,
    *,
    test_events: Iterable[tuple[str, list]] | None = None,
) -> IntelPipeline:
    """Build a deterministic IntelPipeline.

    Args:
        config: Resolved configuration. Defaults to `IntelConfig.from_env()`.
        test_events: Optional `[(source_id, [RawEvent, ...]), ...]` map for
            seeding `InMemoryCrawler`. Tests use this so `pipeline.run()`
            produces a deterministic digest without real RSS fetches.

    Returns:
        Pipeline whose collaborators are taken from `config` where set,
        otherwise from in-memory defaults.
    """

    cfg = config or IntelConfig.from_env()

    crawler = cfg.crawler or InMemoryCrawler(
        {sid: list(evs) for sid, evs in (test_events or [])}
    )
    hash_store = cfg.hash_store or InMemoryHashStore()
    semantic_index = cfg.semantic_index or InMemorySemanticIndex()
    macro = cfg.macro or InMemoryMacroSource([])
    event_store = cfg.event_store or InMemoryEventStore()

    return IntelPipeline(
        sources=list(cfg.sources),
        crawler=crawler,
        hash_gate=HashGate(hash_store),
        semantic_gate=SemanticGate(semantic_index, embed=_default_embed),
        macro=macro,
        event_store=event_store,
    )


async def _default_embed(text: str) -> list[float]:
    """Cheap deterministic embedding for the in-memory smoke path.

    Production replaces this with the LLM router's `embed()` call when the
    real semantic index is wired.
    """
    return hash_embed(text)

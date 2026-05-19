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
        if not sources_path and os.environ.get("INTEL_AUTOSTART", "0") == "1":
            # P2.1 — autostart mode (production) auto-discovers the
            # default sources.yaml so the pipeline is never bound to an
            # empty source list at boot. Tests that import the factory
            # do not set INTEL_AUTOSTART, so the discovery is opt-in.
            for candidate in (
                Path("/app/sources.yaml"),
                Path("apps/agent_intelligence/sources.yaml"),
            ):
                if candidate.exists():
                    sources_path = str(candidate)
                    break
        if sources_path and Path(sources_path).exists():
            srcs = sources_mod.load_sources(sources_path)

        crawler = _build_crawler_from_env()
        hash_store = _build_hash_store_from_env()
        semantic_index = _build_semantic_index_from_env()
        macro = _build_macro_source_from_env()
        event_store = _build_event_store_from_env()
        return cls(
            sources=srcs,
            crawler=crawler,
            hash_store=hash_store,
            semantic_index=semantic_index,
            macro=macro,
            event_store=event_store,
        )


def _build_crawler_from_env() -> CrawlerProtocol | None:
    backend = os.environ.get("INTEL_CRAWLER_BACKEND", "").lower()
    if backend in ("rss", "live"):
        from .crawler.rss import RSSCrawler

        return RSSCrawler()
    if backend == "gdelt":
        from .crawler.gdelt import GdeltCrawler

        return GdeltCrawler()
    if backend == "rss+gdelt":
        # The pipeline iterates over `sources` and dispatches by id prefix.
        # The composite crawler routes "gdelt" sources to GdeltCrawler and
        # the rest to RSSCrawler.
        from .crawler.gdelt import GdeltCrawler
        from .crawler.rss import RSSCrawler

        return _CompositeCrawler(rss=RSSCrawler(), gdelt=GdeltCrawler())
    return None


class _CompositeCrawler:
    """Multiplex RSS + GDELT by source.id prefix.

    The pipeline calls ``fetch(source)`` once per source; we pick the
    crawler by ``source.id`` to keep both data streams in one pipeline
    pass.
    """

    __slots__ = ("_rss", "_gdelt")

    def __init__(self, *, rss, gdelt) -> None:
        self._rss = rss
        self._gdelt = gdelt

    def fetch(self, source):
        if source.id.startswith("gdelt"):
            return self._gdelt.fetch(source)
        return self._rss.fetch(source)


def _build_hash_store_from_env() -> HashStore | None:
    backend = os.environ.get("INTEL_HASH_STORE_BACKEND", "").lower()
    if backend == "redis":
        from .dedupe.redis_hash_gate import RedisHashStore

        return RedisHashStore.from_env()
    return None


def _build_semantic_index_from_env() -> SemanticIndex | None:
    backend = os.environ.get("INTEL_SEMANTIC_INDEX_BACKEND", "").lower()
    if backend == "pgvector":
        from .dedupe.pgvector_index import PgvectorSemanticIndex

        return PgvectorSemanticIndex.from_env()
    return None


def _build_macro_source_from_env() -> MacroSource | None:
    backend = os.environ.get("INTEL_MACRO_BACKEND", "").lower()
    if backend == "fred":
        from .macro.fred import FredMacroSource

        return FredMacroSource.from_env()
    return None


def _build_event_store_from_env() -> EventStore | None:
    backend = os.environ.get("INTEL_EVENT_STORE_BACKEND", "").lower()
    if backend == "postgres":
        from .persistence import PostgresEventStore

        return PostgresEventStore.from_env()
    return None


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
    """Embedding function for the semantic dedupe gate (P2.4).

    Resolution order:
    1. ``INTEL_EMBED_BACKEND=llm`` → route through the LLM router's
       ``embed("intel.dedupe.embed", [text])`` and return the first
       vector. Production path.
    2. Anything else → cheap deterministic ``hash_embed(text)``. Keeps
       the in-memory smoke path and unit tests fast / hermetic.
    """
    backend = os.environ.get("INTEL_EMBED_BACKEND", "").lower()
    if backend == "llm":
        from llm_client.router import embed as router_embed

        resp = await router_embed("intel.dedupe.embed", [text])
        if not resp.vectors:
            raise RuntimeError("intel.dedupe.embed returned no vectors")
        return list(resp.vectors[0])
    return hash_embed(text)

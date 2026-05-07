"""End-to-end pipeline orchestration (workflow 10 §3 architecture).

Stitches: crawler → hash gate → semantic gate → translate → sentiment →
persist → synth → brief → dashboard. Pluggable so tests can run the whole
loop without external services.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import ulid

from . import bias_balance as bb
from . import brief as brief_mod
from . import dashboard as dashboard_mod
from . import sentiment as sentiment_mod
from . import synth as synth_mod
from . import translate as translate_mod
from .crawler.protocol import CrawlerProtocol
from .dedupe.hash_gate import HashGate
from .dedupe.semantic_gate import SemanticGate
from .macro import MacroSource
from .persistence import EventStore, event_hash
from .sources import by_id
from .types import Event, RawEvent, SourceCfg

log = logging.getLogger(__name__)


@dataclass(slots=True)
class PipelineResult:
    digest: object  # IntelDigestV1
    brief: object  # IntelBriefV1
    dashboard: object  # IntelDashboardV1
    accepted_events: list[Event] = field(default_factory=list)
    dropped_hash: int = 0
    dropped_semantic: int = 0


@dataclass(slots=True)
class IntelPipeline:
    sources: list[SourceCfg]
    crawler: CrawlerProtocol
    hash_gate: HashGate
    semantic_gate: SemanticGate
    macro: MacroSource
    event_store: EventStore

    async def run(
        self,
        *,
        macro_regime: str = "unknown",
        asof: datetime | None = None,
    ) -> PipelineResult:
        when = asof or datetime.now(UTC)
        accepted: list[Event] = []
        dropped_hash = 0
        dropped_semantic = 0

        for source in self.sources:
            async for raw in self.crawler.fetch(source):
                if not await self.hash_gate.accept(raw):
                    dropped_hash += 1
                    continue
                ok, _dup_id = await self.semantic_gate.accept(raw)
                if not ok:
                    dropped_semantic += 1
                    continue
                event = await _to_event(raw, source)
                hkey = event_hash(event)
                inserted = await self.event_store.insert(event, hash_key=hkey)
                if inserted:
                    accepted.append(event)

        releases = await self.macro.fetch(when)
        digest = await synth_mod.synthesize(
            accepted,
            macro_releases=releases,
            macro_regime=macro_regime,
            sources=self.sources,
            asof=when,
        )
        brief = await brief_mod.compose(digest)
        dash = dashboard_mod.from_digest(digest)
        return PipelineResult(
            digest=digest,
            brief=brief,
            dashboard=dash,
            accepted_events=accepted,
            dropped_hash=dropped_hash,
            dropped_semantic=dropped_semantic,
        )


async def _to_event(raw: RawEvent, source: SourceCfg) -> Event:
    title_en, body_en = await translate_mod.translate(raw)
    sent = await sentiment_mod.classify(title_en, body_en)
    return Event(
        id=str(ulid.ULID()),
        source_id=raw.source_id,
        source_region=source.region,
        source_lean=source.lean,
        event_ts=raw.event_ts,
        title=raw.title,
        body=raw.body,
        title_en=title_en,
        body_en=body_en,
        lang=raw.lang,
        sentiment=sent.valence,
        target_assets=list(sent.target_assets),
        url=raw.url,
    )


def source_lookup(sources: Iterable[SourceCfg]) -> dict[str, SourceCfg]:
    return by_id(list(sources))


def _bias(events: list[Event], sources: list[SourceCfg]) -> object:
    return bb.compute(events, bb.weights_from(sources))

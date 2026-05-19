"""FUTU subscription manager (P4.5).

Tracks the active set of (ticker, subtype) subscriptions for one FutuQuoteClient.
State lives in NATS KV under ``iic_state/futu_subs`` so a restart can
reconcile the in-memory view against what OpenD already has subscribed,
avoiding double-counting against the per-tier subscription budget.

The state shape is intentionally simple: a JSON-serialisable dict of
``{ subtype: [ticker, ...] }`` per FutuQuoteClient. The hot path is
``add(tickers, subtype)`` / ``remove(tickers, subtype)`` plus the
periodic ``reconcile()`` that compares the desired set vs OpenD's
declared set.

The KV bucket is optional — when not provided we fall back to an
in-process dict so unit tests don't need NATS.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Protocol

import orjson

log = logging.getLogger(__name__)


class _KvStore(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def put(self, key: str, value: bytes) -> None: ...


class InMemoryKv:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self._data.get(key)

    async def put(self, key: str, value: bytes) -> None:
        self._data[key] = value


@dataclass(slots=True)
class FutuSubscriptionManager:
    """Owns the desired-subscription set for one quote client + persists it."""

    quote: Any  # FutuQuoteClient — declared as Any to avoid the import cycle.
    kv: _KvStore = field(default_factory=InMemoryKv)
    state_key: str = "iic_state/futu_subs"
    subs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    async def load(self) -> None:
        raw = await self.kv.get(self.state_key)
        if not raw:
            return
        try:
            doc = orjson.loads(raw)
        except orjson.JSONDecodeError:
            log.warning("sub_manager: bad KV payload; starting clean")
            return
        for subtype, tickers in doc.items():
            self.subs[subtype] = set(tickers or [])

    async def _persist(self) -> None:
        doc = {st: sorted(s) for st, s in self.subs.items()}
        await self.kv.put(self.state_key, orjson.dumps(doc))

    async def add(self, tickers: list[str], subtype: str = "QUOTE") -> dict[str, Any]:
        new = [t for t in tickers if t not in self.subs[subtype]]
        if new:
            self.quote.subscribe(code_list=new, subtype_list=[subtype])
            self.subs[subtype].update(new)
            await self._persist()
        return {"added": new, "current_count": len(self.subs[subtype])}

    async def remove(self, tickers: list[str], subtype: str = "QUOTE") -> dict[str, Any]:
        gone = [t for t in tickers if t in self.subs[subtype]]
        if gone:
            self.quote.unsubscribe(code_list=gone, subtype_list=[subtype])
            self.subs[subtype].difference_update(gone)
            await self._persist()
        return {"removed": gone, "current_count": len(self.subs[subtype])}

    def list(self, subtype: str = "QUOTE") -> list[str]:
        return sorted(self.subs[subtype])

    async def reconcile(self) -> dict[str, Any]:
        """Re-issue every subscribe so OpenD's view matches ours after restart."""
        out: dict[str, list[str]] = {}
        for subtype, tickers in self.subs.items():
            if not tickers:
                continue
            self.quote.subscribe(code_list=sorted(tickers), subtype_list=[subtype])
            out[subtype] = sorted(tickers)
        return {"reconciled": out}

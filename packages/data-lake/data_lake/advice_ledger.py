"""Hash-chained, append-only advice ledger writer + verifier (workflow 02 §5.4).

Defense in depth:
  - Python-side computes row_hash and inserts via SELECT FOR UPDATE on the
    last row for that agent. Concurrent inserts collide on the
    (agent, prev_hash) unique index.
  - SQL trigger (migration 0002) re-computes row_hash server-side and
    rejects writes whose payload doesn't hash-match.
  - lake.advice has UPDATE/DELETE revoked from iic_app — once written, only
    a DBA can touch it.

verify_chain(agent) recomputes the entire chain from the payloads. A break
returns the id of the first bad row (or 'empty' if no rows exist).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

import orjson
from sqlalchemy import text

from data_lake.exceptions import AdviceLedgerError
from data_lake.postgres import session

ChainStatusKind = Literal["ok", "broken", "empty"]


@dataclass(frozen=True, slots=True)
class ChainStatus:
    kind: ChainStatusKind
    agent: str
    rows_checked: int
    broken_at_id: str | None = None


def _canonical_json(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTC datetimes as Z."""
    return orjson.dumps(
        payload,
        option=orjson.OPT_SORT_KEYS | orjson.OPT_NAIVE_UTC | orjson.OPT_UTC_Z,
    )


def compute_row_hash(prev_hash: bytes | None, payload: dict[str, Any]) -> bytes:
    """sha256(prev_hash || canonical_json(payload)). prev_hash=None for the first row."""
    h = hashlib.sha256()
    if prev_hash is not None:
        h.update(prev_hash)
    h.update(_canonical_json(payload))
    return h.digest()


async def _select_chain_head(s: Any, agent: str) -> bytes | None:
    """Read the latest row_hash for `agent` under FOR UPDATE."""
    row = await s.execute(
        text(
            "SELECT row_hash FROM lake.advice "
            "WHERE agent = :agent "
            "ORDER BY issued_at DESC, id DESC "
            "LIMIT 1 FOR UPDATE"
        ),
        {"agent": agent},
    )
    head = row.first()
    return bytes(head[0]) if head else None


async def append(advice: dict[str, Any]) -> bytes:
    """Insert one advice payload. Returns the row_hash that was committed.

    `advice` must be the canonical advice.v1 envelope as a dict (use
    AdviceV1.model_dump(mode='json') from packages/schema first).
    Concurrent appenders for the same agent will collide on the unique
    (agent, prev_hash) index — the loser raises an IntegrityError and
    should retry.
    """
    required = (
        "schema",
        "id",
        "agent",
        "issued_at",
        "asset",
        "thesis",
        "direction",
        "confidence",
        "entry_band",
        "target_band",
        "stop_loss",
        "horizon_days",
        "max_drawdown_pct",
        "expires_at",
        "evidence",
    )
    missing = [k for k in required if k not in advice]
    if missing:
        raise AdviceLedgerError(f"advice payload missing required keys: {missing}")
    if not advice["evidence"]:
        raise AdviceLedgerError("advice rejected: empty evidence (uncited)")

    agent = advice["agent"]
    asset = advice["asset"]
    entry_lo, entry_hi = advice["entry_band"]
    target_lo, target_hi = advice["target_band"]

    canonical = _canonical_json(advice)

    async with session("app") as s:
        prev_hash = await _select_chain_head(s, agent)
        row_hash = compute_row_hash(prev_hash, advice)
        await s.execute(
            text(
                "INSERT INTO lake.advice ("
                "  id, schema, agent, issued_at, "
                "  asset_kind, asset_ticker, asset_venue, asset_name, "
                "  thesis, direction, confidence, "
                "  entry_low, entry_high, target_low, target_high, "
                "  stop_loss, horizon_days, max_drawdown_pct, sizing_hint_pct_nav, "
                "  expires_at, evidence, payload, payload_canonical, prev_hash, row_hash"
                ") VALUES ("
                "  :id, :schema, :agent, :issued_at, "
                "  :asset_kind, :asset_ticker, :asset_venue, :asset_name, "
                "  :thesis, :direction, :confidence, "
                "  :entry_low, :entry_high, :target_low, :target_high, "
                "  :stop_loss, :horizon_days, :max_drawdown_pct, :sizing_hint_pct_nav, "
                "  :expires_at, :evidence::jsonb, :payload::jsonb, "
                "  :payload_canonical, :prev_hash, :row_hash"
                ")"
            ),
            {
                "id": advice["id"],
                "schema": advice["schema"],
                "agent": agent,
                "issued_at": advice["issued_at"],
                "asset_kind": asset["kind"],
                "asset_ticker": asset["ticker"],
                "asset_venue": asset.get("venue"),
                "asset_name": asset.get("name"),
                "thesis": advice["thesis"],
                "direction": advice["direction"],
                "confidence": advice["confidence"],
                "entry_low": entry_lo,
                "entry_high": entry_hi,
                "target_low": target_lo,
                "target_high": target_hi,
                "stop_loss": advice["stop_loss"],
                "horizon_days": advice["horizon_days"],
                "max_drawdown_pct": advice["max_drawdown_pct"],
                "sizing_hint_pct_nav": advice.get("sizing_hint_pct_nav"),
                "expires_at": advice["expires_at"],
                "evidence": orjson.dumps(advice["evidence"]).decode(),
                "payload": canonical.decode(),
                "payload_canonical": canonical,
                "prev_hash": prev_hash,
                "row_hash": row_hash,
            },
        )
    return row_hash


async def verify_chain(agent: str) -> ChainStatus:
    """Recompute the chain for `agent` from the stored canonical bytes.

    Hashing the byte column (not the JSONB roundtrip) is what makes this
    deterministic — Postgres' JSONB text serialization is not byte-identical
    to orjson's canonical output, so re-canonicalizing the deserialized dict
    would spuriously diverge.
    """
    async with session("ro") as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id, payload_canonical, prev_hash, row_hash FROM lake.advice "
                    "WHERE agent = :agent "
                    "ORDER BY issued_at ASC, id ASC"
                ),
                {"agent": agent},
            )
        ).all()

    if not rows:
        return ChainStatus(kind="empty", agent=agent, rows_checked=0)

    prev_hash: bytes | None = None
    for i, (row_id, payload_canonical, db_prev, db_row_hash) in enumerate(rows):
        h = hashlib.sha256()
        if prev_hash is not None:
            h.update(prev_hash)
        h.update(bytes(payload_canonical))
        expected = h.digest()
        if bytes(db_row_hash) != expected:
            return ChainStatus(kind="broken", agent=agent, rows_checked=i + 1, broken_at_id=row_id)
        if prev_hash is not None and (db_prev is None or bytes(db_prev) != prev_hash):
            return ChainStatus(kind="broken", agent=agent, rows_checked=i + 1, broken_at_id=row_id)
        prev_hash = expected

    return ChainStatus(kind="ok", agent=agent, rows_checked=len(rows))

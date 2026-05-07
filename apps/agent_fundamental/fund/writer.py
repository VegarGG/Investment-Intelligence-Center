"""Composes advice.fundamental.v1 (workflow 11 §5.4) + citation guard (§7)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import ulid
from llm_client import ChatMessage, chat
from schema import AdviceV1, Asset, Direction, Evidence

from .types import Fundamentals, ValuationCase, WatchlistEntry

INSUFFICIENT_DATA_THRESHOLD = 0.30
HORIZON_DAYS = 90
NUMERIC_PATTERNS = [
    re.compile(r"\d+(?:\.\d+)?\s?%"),
    re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?"),
    re.compile(r"\d+(?:\.\d+)?\s?(?:x|×)"),
]
CITATION_RE = re.compile(r"\[(?:ref|cite|source)[^\]]*\]")


class CitationGuardError(ValueError):
    """Raised when the thesis carries numeric claims without inline citations."""


class InsufficientData(ValueError):
    """Raised by `compose` when fundamentals are missing > 30% of inputs."""


@dataclass(frozen=True, slots=True)
class WriterContext:
    entry: WatchlistEntry
    fundamentals: Fundamentals
    valuation: ValuationCase
    current_price: float


def guard_citations(thesis: str) -> None:
    """Every numeric claim must be followed by a citation marker within 50 chars.

    Raises `CitationGuardError` with a message naming the first offender.
    """
    for pat in NUMERIC_PATTERNS:
        for match in pat.finditer(thesis):
            window = thesis[match.end() : match.end() + 50]
            if not CITATION_RE.search(window):
                raise CitationGuardError(
                    f"numeric claim {match.group()!r} lacks a citation within 50 chars"
                )


def derive_direction(target_mid: float, current_price: float) -> Direction:
    if current_price <= 0:
        return "flat"
    ratio = target_mid / current_price
    if ratio > 1.10:
        return "long"
    if ratio < 0.90:
        return "short"
    return "flat"


async def compose(
    ctx: WriterContext,
    *,
    digest_event_id: str | None = None,
    filing_url: str | None = None,
    filing_chunk_ref: str | None = None,
) -> AdviceV1:
    if ctx.fundamentals.missing_pct > INSUFFICIENT_DATA_THRESHOLD:
        raise InsufficientData(
            f"{ctx.entry.ticker}: fundamentals missing "
            f"{ctx.fundamentals.missing_pct * 100:.0f}% (>30%)"
        )

    target_mid = (ctx.valuation.bear + ctx.valuation.bull) / 2
    direction = derive_direction(target_mid, ctx.current_price)

    response = await chat(
        caller_id="fund.writer",
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "Write a 4-6 sentence equity thesis. "
                    "Append [ref:filing] or [ref:digest] markers after every "
                    "numeric claim (percentages, multiples, $ amounts)."
                ),
            ),
            ChatMessage(
                role="user",
                content=(
                    f"Ticker={ctx.entry.ticker} "
                    f"sector={ctx.entry.sector} "
                    f"current={ctx.current_price:.2f} "
                    f"base={ctx.valuation.base:.2f} "
                    f"bull={ctx.valuation.bull:.2f} "
                    f"bear={ctx.valuation.bear:.2f} "
                    f"assumptions={'; '.join(ctx.valuation.assumptions)}"
                ),
            ),
        ],
        max_tokens=600,
        temperature=0.2,
    )
    thesis = response.text.strip()
    guard_citations(thesis)

    now = datetime.now(UTC)
    evidence: list[Evidence] = []
    if filing_url:
        evidence.append(Evidence(kind="filing", url=filing_url, ref=filing_chunk_ref or ""))
    if digest_event_id:
        evidence.append(Evidence(kind="news", ref=f"intel.digest.v1#{digest_event_id}"))
    evidence.append(Evidence(kind="filing_url", ref=f"lake.timeseries:{ctx.entry.ticker}"))

    entry_low, entry_high = _entry_band(ctx.current_price, direction)
    target_low, target_high = ctx.valuation.bear, ctx.valuation.bull
    stop_loss = _stop_loss(ctx.current_price, direction)

    return AdviceV1(
        id=str(ulid.ULID()),
        agent="fundamental",
        issued_at=now,
        asset=Asset(kind="equity", ticker=ctx.entry.ticker, venue=ctx.entry.venue),
        thesis=thesis,
        direction=direction,
        confidence=_confidence(ctx.valuation, ctx.current_price),
        entry_band=(entry_low, entry_high),
        target_band=(target_low, target_high),
        stop_loss=stop_loss,
        horizon_days=HORIZON_DAYS,
        max_drawdown_pct=12.0,
        sizing_hint_pct_nav=2.5,
        expires_at=now + timedelta(days=HORIZON_DAYS),
        evidence=evidence,
    )


def _entry_band(current: float, direction: Direction) -> tuple[float, float]:
    if direction == "long":
        return (current * 0.97, current * 1.01)
    if direction == "short":
        return (current * 0.99, current * 1.03)
    return (current, current)


def _stop_loss(current: float, direction: Direction) -> float:
    if direction == "long":
        return current * 0.92
    if direction == "short":
        return current * 1.08
    return current


def _confidence(case: ValuationCase, current: float) -> float:
    if current <= 0:
        return 0.05
    spread = (case.bull - case.bear) / current if current else 1.0
    base = max(0.05, min(0.9, 0.6 - spread))
    return round(base, 3)

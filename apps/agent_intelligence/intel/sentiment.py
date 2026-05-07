"""Sentiment + asset extraction (workflow 10 §5.5).

Two-stage: VADER for a fast valence baseline, then DeepSeek Flash for
finance-aware classification. The Flash call is only invoked if the
title mentions a probable ticker (uppercase 1-5 char run); otherwise
we save the round-trip and use VADER alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from llm_client import ChatMessage, chat

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{2,4})?\b")
_VADER_NEG = ("crash", "plunge", "fail", "loss", "scandal", "default", "bankrupt")
_VADER_POS = ("surge", "beat", "rally", "record", "growth", "approve", "expand")


@dataclass(frozen=True, slots=True)
class SentimentResult:
    valence: float  # -1..1
    target_assets: tuple[str, ...]
    used_llm: bool


def vader_score(text: str) -> float:
    """Lightweight valence — finance keywords + simple polarity. Negative
    when negative words outnumber positive ones, scaled to [-1, 1]."""
    lower = text.lower()
    pos = sum(lower.count(w) for w in _VADER_POS)
    neg = sum(lower.count(w) for w in _VADER_NEG)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def candidate_tickers(text: str) -> list[str]:
    """Pull uppercase runs that *look* like tickers — false positives are
    pruned downstream against `lake.symbol_master`."""
    return _TICKER_RE.findall(text)


async def classify(title: str, body: str) -> SentimentResult:
    """Run VADER; if any candidate tickers appear in the title, escalate
    to a Flash call for finance-aware tagging."""
    text = f"{title}\n{body}"
    valence = vader_score(text)
    tickers = candidate_tickers(title)

    if not tickers:
        return SentimentResult(valence=valence, target_assets=(), used_llm=False)

    response = await chat(
        caller_id="intel.sentiment.classify",
        messages=[
            ChatMessage(
                role="system",
                content=(
                    "You are a finance-aware sentiment tagger. "
                    "Output two CSV lines: line1=valence in [-1,1], "
                    "line2=comma-separated tickers actually mentioned (no fabrication)."
                ),
            ),
            ChatMessage(role="user", content=f"Headline: {title}\nBody: {body}"),
        ],
        max_tokens=200,
        temperature=0.0,
    )
    llm_valence, llm_tickers = _parse_response(response.text, fallback_valence=valence)
    return SentimentResult(
        valence=llm_valence,
        target_assets=tuple(t for t in llm_tickers if t in tickers),
        used_llm=True,
    )


def _parse_response(text: str, *, fallback_valence: float) -> tuple[float, list[str]]:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return fallback_valence, []
    try:
        valence = max(-1.0, min(1.0, float(lines[0].split(",")[0])))
    except (ValueError, IndexError):
        valence = fallback_valence
    tickers: list[str] = []
    if len(lines) > 1:
        tickers = [t.strip().upper() for t in lines[1].split(",") if t.strip()]
    return valence, tickers

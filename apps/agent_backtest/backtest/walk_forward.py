"""Walk-forward backtest harness (v2.5 T1.12).

Plan §T1.12: given a prompt-version bump, re-run the past 24 months
walk-forward with the new prompts and produce a delta vs the prior
version. CI fails if a prompt change lands without a green walk-forward
delta or an explicit ``[walk-forward override: <reason>]`` in the PR
title (cap one override / quarter via the same PR-title token).

Two layers:
- ``WalkForwardHarness`` — replays a fixture of historical advice and
  computes per-prompt-version metrics (alpha, hit-rate, max DD).
- ``compare()`` — diffs two ``WalkForwardReport`` instances and decides
  pass / fail per the configurable thresholds.

Default thresholds (plan §T1.12):
- Material negative = (alpha drop > 10pp) OR (hit-rate drop > 5pp).
- Override: PR title contains ``[walk-forward override: ...]``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

# Plan §T1.12 acceptance thresholds. ``alpha`` is a fraction (0.10 = 10pp).
DEFAULT_ALPHA_DROP_THRESHOLD = 0.10
DEFAULT_HIT_RATE_DROP_THRESHOLD = 0.05
OVERRIDE_TITLE_RE = re.compile(r"\[walk-forward override:\s*(?P<reason>.+?)\]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class HistoricalAdvice:
    """One row from the replay fixture."""

    advice_id: str
    issued_at: datetime
    ticker: str
    direction: Literal["long", "short", "flat"]
    entry_px: float
    realized_exit_px: float
    realized_pnl_pct: float
    benchmark_pnl_pct: float
    realized_max_dd_pct: float
    held: bool


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    prompt_version: str
    start: date
    end: date
    sample_size: int
    avg_alpha: float
    hit_rate: float
    avg_max_dd_pct: float

    def summary(self) -> dict[str, float | int | str]:
        return {
            "prompt_version": self.prompt_version,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "sample_size": self.sample_size,
            "avg_alpha": round(self.avg_alpha, 4),
            "hit_rate": round(self.hit_rate, 4),
            "avg_max_dd_pct": round(self.avg_max_dd_pct, 4),
        }


@dataclass(frozen=True, slots=True)
class WalkForwardDelta:
    baseline: WalkForwardReport
    candidate: WalkForwardReport
    alpha_delta: float        # candidate - baseline
    hit_rate_delta: float
    max_dd_delta: float       # candidate - baseline (negative = better)
    materially_negative: bool

    def summary(self) -> dict[str, object]:
        return {
            "baseline": self.baseline.summary(),
            "candidate": self.candidate.summary(),
            "alpha_delta": round(self.alpha_delta, 4),
            "hit_rate_delta": round(self.hit_rate_delta, 4),
            "max_dd_delta": round(self.max_dd_delta, 4),
            "materially_negative": self.materially_negative,
        }


@dataclass(slots=True)
class WalkForwardHarness:
    """Replays a sequence of HistoricalAdvice through a prompt-tagged scorer.

    The scorer is intentionally pure-Python (no LLM call) so the harness
    is deterministic. Real prompt-version effects show up because the
    advice fixtures themselves carry the prompt-version tag, and the
    scorer can be swapped per version.
    """

    history: Sequence[HistoricalAdvice]

    def run(self, *, prompt_version: str, scorer: "AdviceScorer | None" = None) -> WalkForwardReport:
        """Score every advice and aggregate. ``scorer`` defaults to the
        identity scorer that uses the historical realized fields."""

        scorer = scorer or _identity_scorer
        scored = [scorer(a) for a in self.history]
        if not scored:
            return WalkForwardReport(
                prompt_version=prompt_version,
                start=date.today(),
                end=date.today(),
                sample_size=0,
                avg_alpha=0.0,
                hit_rate=0.0,
                avg_max_dd_pct=0.0,
            )

        alphas = [s.realized_pnl_pct - s.benchmark_pnl_pct for s in scored]
        hits = sum(1 for s in scored if s.held)
        return WalkForwardReport(
            prompt_version=prompt_version,
            start=min(s.issued_at.date() for s in scored),
            end=max(s.issued_at.date() for s in scored),
            sample_size=len(scored),
            avg_alpha=sum(alphas) / len(alphas),
            hit_rate=hits / len(scored),
            avg_max_dd_pct=sum(s.realized_max_dd_pct for s in scored) / len(scored),
        )


AdviceScorer = "callable[[HistoricalAdvice], HistoricalAdvice]"


def _identity_scorer(a: HistoricalAdvice) -> HistoricalAdvice:
    return a


def compare(
    baseline: WalkForwardReport,
    candidate: WalkForwardReport,
    *,
    alpha_drop_threshold: float = DEFAULT_ALPHA_DROP_THRESHOLD,
    hit_rate_drop_threshold: float = DEFAULT_HIT_RATE_DROP_THRESHOLD,
) -> WalkForwardDelta:
    """Return a delta + the materially-negative flag the CI gate reads."""
    alpha_delta = candidate.avg_alpha - baseline.avg_alpha
    hit_rate_delta = candidate.hit_rate - baseline.hit_rate
    max_dd_delta = candidate.avg_max_dd_pct - baseline.avg_max_dd_pct
    materially_negative = (
        alpha_delta < -alpha_drop_threshold
        or hit_rate_delta < -hit_rate_drop_threshold
    )
    return WalkForwardDelta(
        baseline=baseline,
        candidate=candidate,
        alpha_delta=alpha_delta,
        hit_rate_delta=hit_rate_delta,
        max_dd_delta=max_dd_delta,
        materially_negative=materially_negative,
    )


def has_override(pr_title: str) -> tuple[bool, str | None]:
    """Detect ``[walk-forward override: <reason>]`` in a PR title."""
    m = OVERRIDE_TITLE_RE.search(pr_title or "")
    if m is None:
        return False, None
    return True, m.group("reason").strip()


def write_report(delta: WalkForwardDelta, out_dir: Path) -> Path:
    """Persist the delta JSON for the CI gate + dashboard."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"walk_forward_{delta.candidate.prompt_version}.json"
    path.write_text(json.dumps(delta.summary(), indent=2, default=str))
    return path


def replay_from_jsonl(path: Path) -> list[HistoricalAdvice]:
    """Materialise a HistoricalAdvice list from a JSONL fixture file."""
    out: list[HistoricalAdvice] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(
            HistoricalAdvice(
                advice_id=d["advice_id"],
                issued_at=datetime.fromisoformat(d["issued_at"]).astimezone(UTC),
                ticker=d["ticker"],
                direction=d["direction"],
                entry_px=float(d["entry_px"]),
                realized_exit_px=float(d["realized_exit_px"]),
                realized_pnl_pct=float(d["realized_pnl_pct"]),
                benchmark_pnl_pct=float(d["benchmark_pnl_pct"]),
                realized_max_dd_pct=float(d["realized_max_dd_pct"]),
                held=bool(d["held"]),
            )
        )
    return out

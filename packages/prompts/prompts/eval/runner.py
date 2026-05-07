"""Eval runner — replay golden_set.yaml entries and aggregate scores
(workflow 04 §5.2, §6.5).

Two consumption paths:
  1. Programmatic — `await run(caller_id="intel.synth")`.
  2. CLI — `python -m prompts.eval.runner --caller intel.synth`.

The runner writes one JSONL row per (entry, version) pair to `snapshot_dir`
when supplied, so the eval harness deterministically replayable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .judge import JudgeResult, build_judge_prompt, parse_judge_response

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.yaml"


class GoldenEntry(BaseModel):
    id: str
    caller_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    rubric: list[str]
    reference_answer_excerpt: str | None = None
    notes: str | None = None


class EntryResult(BaseModel):
    entry_id: str
    caller_id: str
    version: str
    overall_score: float
    rubric_scores: dict[str, float]
    candidate_answer: str
    judge_notes: str


class EvalReport(BaseModel):
    total_entries: int
    per_caller_mean: dict[str, float]
    per_entry: list[EntryResult]
    overall_mean: float


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[GoldenEntry]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [GoldenEntry.model_validate(item) for item in raw]


def coverage_report(entries: list[GoldenEntry]) -> dict[str, int]:
    """Count entries per caller — used by the §8 acceptance criterion
    (>=3 per active caller)."""
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.caller_id] += 1
    return dict(counts)


async def _run_one(
    entry: GoldenEntry,
    *,
    chat_fn: Any,
    version: str | None,
) -> EntryResult:
    """Execute one entry: render prompt → call LLM → judge.

    chat_fn is the async chat callable from `llm_client.router.chat` —
    injected so the runner can be tested without a real LLM."""
    from llm_client.types import ChatMessage

    from ..registry import get

    prompt = get(entry.caller_id, version=version, **entry.inputs)
    messages = []
    if prompt.system:
        messages.append(ChatMessage(role="system", content=prompt.system))
    messages.append(ChatMessage(role="user", content=prompt.user))

    candidate_resp = await chat_fn(
        caller_id=entry.caller_id,
        messages=messages,
        force_tier=prompt.tier,
        temperature=0.0,
    )
    candidate_text = candidate_resp.text

    judge_prompt = build_judge_prompt(
        caller_id=entry.caller_id,
        inputs={k: str(v) for k, v in entry.inputs.items()},
        rubric=entry.rubric,
        candidate_answer=candidate_text,
    )
    judge_resp = await chat_fn(
        caller_id="eval.judge",
        messages=[
            ChatMessage(role="system", content=judge_prompt.system or ""),
            ChatMessage(role="user", content=judge_prompt.user),
        ],
        force_tier="pro",
        temperature=0.0,
    )
    parsed: JudgeResult = parse_judge_response(judge_resp.text, entry.rubric)

    return EntryResult(
        entry_id=entry.id,
        caller_id=entry.caller_id,
        version=prompt.version,
        overall_score=parsed.overall_score,
        rubric_scores=parsed.rubric_scores,
        candidate_answer=candidate_text,
        judge_notes=parsed.notes,
    )


async def run(
    *,
    caller_id: str | None = None,
    version: str | None = None,
    snapshot_dir: Path | None = None,
    chat_fn: Any = None,
) -> EvalReport:
    """Replay the golden set, aggregating per-caller and overall scores.

    chat_fn may be injected for tests; in production it's
    `llm_client.router.chat`."""
    if chat_fn is None:
        from llm_client.router import chat as default_chat

        chat_fn = default_chat

    entries = load_golden_set()
    if caller_id is not None:
        entries = [e for e in entries if e.caller_id == caller_id]

    results: list[EntryResult] = []
    for entry in entries:
        result = await _run_one(entry, chat_fn=chat_fn, version=version)
        results.append(result)
        if snapshot_dir is not None:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            (snapshot_dir / f"{entry.id}.json").write_text(
                result.model_dump_json(indent=2), encoding="utf-8"
            )

    by_caller: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_caller[r.caller_id].append(r.overall_score)
    per_caller_mean = {c: sum(s) / len(s) for c, s in by_caller.items()}
    overall = sum(r.overall_score for r in results) / len(results) if results else 0.0

    return EvalReport(
        total_entries=len(results),
        per_caller_mean=per_caller_mean,
        per_entry=results,
        overall_mean=overall,
    )


def _print_table(report: EvalReport) -> None:
    print(
        f"\nEval report — {report.total_entries} entries, "
        f"overall mean {report.overall_mean:.3f}\n"
    )
    print(f"{'caller_id':<30} {'mean':>6}")
    print("-" * 38)
    for caller, mean in sorted(report.per_caller_mean.items()):
        print(f"{caller:<30} {mean:>6.3f}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the prompt eval harness.")
    parser.add_argument("--caller", help="Filter to one caller_id")
    parser.add_argument("--against-version", help="Pin a specific version")
    parser.add_argument("--snapshot-dir", type=Path, help="Write JSON snapshots here")
    parser.add_argument("--json", action="store_true", help="Emit the EvalReport as JSON")
    args = parser.parse_args(argv)
    report = asyncio.run(
        run(
            caller_id=args.caller,
            version=args.against_version,
            snapshot_dir=args.snapshot_dir,
        )
    )
    if args.json:
        json.dump(report.model_dump(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_table(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

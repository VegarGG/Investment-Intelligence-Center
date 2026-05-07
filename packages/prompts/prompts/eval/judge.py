"""Pro-as-judge scoring (workflow 04 §5.3).

The judge prompt is locked at registry/eval.judge/1.0.0.md — drift would
invalidate the entire harness, so it bumps only on explicit major signoff.
Temperature is forced to 0.0 for determinism (workflow 04 §9 — gotcha 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..registry import RenderedPrompt, get


@dataclass(frozen=True, slots=True)
class JudgeResult:
    overall_score: float  # 0..1
    rubric_scores: dict[str, float]  # one entry per rubric line
    notes: str  # free-text rationale from the judge


def build_judge_prompt(
    *,
    caller_id: str,
    inputs: dict[str, str],
    rubric: list[str],
    candidate_answer: str,
) -> RenderedPrompt:
    """Render the locked judge template with this scoring task's payload."""
    return get(
        "eval.judge",
        caller_id_under_test=caller_id,
        inputs_json=_format_inputs(inputs),
        rubric_md=_format_rubric(rubric),
        candidate_answer=candidate_answer,
    )


def _format_inputs(inputs: dict[str, str]) -> str:
    if not inputs:
        return "(none)"
    return "\n".join(f"- **{k}**: {v[:500]}" for k, v in inputs.items())


def _format_rubric(rubric: list[str]) -> str:
    return "\n".join(f"{i + 1}. {item}" for i, item in enumerate(rubric))


_SCORE_PATTERN = re.compile(r"^\s*(\d+)\s*[:.\)]\s*([01](?:\.\d+)?)\s*$", re.M)


def parse_judge_response(text: str, rubric: list[str]) -> JudgeResult:
    """Extract per-rubric scores from the judge's freeform response.

    The judge prompt instructs the model to emit lines like `1: 0.8` followed
    by free-text notes. Missing items default to 0.0 (a clear regression
    signal — better than silently scoring missing rubric items as passing).
    """
    matches = _SCORE_PATTERN.findall(text)
    parsed = {int(idx): float(score) for idx, score in matches if 0.0 <= float(score) <= 1.0}

    rubric_scores: dict[str, float] = {}
    for i, item in enumerate(rubric, start=1):
        rubric_scores[item] = parsed.get(i, 0.0)

    overall = sum(rubric_scores.values()) / len(rubric_scores) if rubric_scores else 0.0
    notes = _SCORE_PATTERN.sub("", text).strip()
    return JudgeResult(overall_score=overall, rubric_scores=rubric_scores, notes=notes)

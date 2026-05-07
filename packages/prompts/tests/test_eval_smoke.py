"""Workflow 04 §5 + acceptance criterion 7 — golden set smoke + judge parsing."""

from __future__ import annotations

from collections import Counter

import pytest
from prompts.eval.judge import JudgeResult, parse_judge_response
from prompts.eval.runner import GOLDEN_SET_PATH, coverage_report, load_golden_set


class TestGoldenSetCoverage:
    """Acceptance: ≥60 entries; ≥3 entries per active caller."""

    def test_at_least_60_entries(self) -> None:
        entries = load_golden_set(GOLDEN_SET_PATH)
        assert len(entries) >= 60, f"only {len(entries)} entries"

    def test_three_entries_per_caller(self) -> None:
        counts = coverage_report(load_golden_set(GOLDEN_SET_PATH))
        thin = {c: n for c, n in counts.items() if n < 3}
        assert not thin, f"callers with < 3 golden entries: {thin}"

    def test_caller_ids_match_registry(self) -> None:
        from prompts.registry import list_callers

        registry_callers = set(list_callers())
        golden_callers = {e.caller_id for e in load_golden_set(GOLDEN_SET_PATH)}
        missing_in_golden = registry_callers - golden_callers
        assert (
            not missing_in_golden
        ), f"registry has callers with no golden entry: {missing_in_golden}"

    def test_entry_ids_are_unique(self) -> None:
        entries = load_golden_set(GOLDEN_SET_PATH)
        dupes = [eid for eid, n in Counter(e.id for e in entries).items() if n > 1]
        assert not dupes, f"duplicate golden entry ids: {dupes}"


class TestJudgeParsing:
    def test_extracts_numbered_scores(self) -> None:
        text = """1: 1.0
2: 0.5
3: 0.0

Rationale: it nailed item 1, half-credit on 2, missed 3."""
        rubric = ["A", "B", "C"]
        result: JudgeResult = parse_judge_response(text, rubric)
        assert result.rubric_scores == {"A": 1.0, "B": 0.5, "C": 0.0}
        assert result.overall_score == pytest.approx(0.5)

    def test_missing_score_defaults_to_zero(self) -> None:
        text = "1: 1.0\n\nRationale: only scored item 1."
        rubric = ["A", "B"]
        result = parse_judge_response(text, rubric)
        assert result.rubric_scores == {"A": 1.0, "B": 0.0}
        # signal that something's wrong — overall drops accordingly
        assert result.overall_score == pytest.approx(0.5)

    def test_invalid_score_ignored(self) -> None:
        text = "1: 2.5\n2: 0.5\n\nRationale: bad."
        rubric = ["A", "B"]
        result = parse_judge_response(text, rubric)
        # 2.5 is out-of-range; A defaults to 0.0
        assert result.rubric_scores == {"A": 0.0, "B": 0.5}

    def test_notes_excludes_score_lines(self) -> None:
        text = "1: 1.0\n\nRationale: short note."
        rubric = ["A"]
        result = parse_judge_response(text, rubric)
        assert "1: 1.0" not in result.notes
        assert "short note" in result.notes


class TestRendering:
    """Make sure every seed prompt actually renders without unbound vars."""

    def test_each_seed_prompt_renders_with_stub_inputs(self) -> None:
        from prompts.frontmatter import parse_file
        from prompts.registry import REGISTRY_ROOT
        from prompts.render import merge_with_defaults, render_body

        for caller_dir in sorted(REGISTRY_ROOT.iterdir()):
            for prompt_file in sorted(caller_dir.glob("*.md")):
                parsed = parse_file(prompt_file)
                # Fabricate plausible values for required vars.
                stub: dict[str, object] = {}
                for var in parsed.frontmatter.variables:
                    if var.required and var.default is None:
                        stub[var.name] = (
                            "[]"
                            if var.type == "json"
                            else (
                                1
                                if var.type == "int"
                                else (
                                    1.0
                                    if var.type == "float"
                                    else True if var.type == "bool" else "stub"
                                )
                            )
                        )
                merged = merge_with_defaults(parsed.frontmatter.variables, stub)
                rendered = render_body(parsed.body, merged)
                assert rendered, f"{prompt_file} rendered empty"


@pytest.mark.integration
class TestRunnerIntegration:
    """Acceptance criterion 2: runner end-to-end against real DeepSeek.

    Skipped unless IIC_INTEGRATION=1 because it needs API keys and spends
    real budget."""

    @pytest.mark.asyncio
    async def test_runner_against_intel_synth(self) -> None:
        from prompts.eval.runner import run

        report = await run(caller_id="intel.synth")
        assert report.total_entries >= 1
        assert "intel.synth" in report.per_caller_mean

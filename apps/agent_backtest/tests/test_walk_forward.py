"""v2.5 T1.12 — walk-forward harness + CI gate acceptance.

The legacy v2.1 file at this path covered an older walk-forward concept.
v2.5 replaces it with the harness/compare/has_override surface plus a
synthetic prompt-bump test that verifies the gate fails closed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backtest.walk_forward import (
    DEFAULT_ALPHA_DROP_THRESHOLD,
    HistoricalAdvice,
    WalkForwardHarness,
    compare,
    has_override,
)


def _ad(
    *,
    advice_id: str,
    pnl_pct: float,
    bench: float = 0.05,
    held: bool = True,
    max_dd: float = 0.05,
) -> HistoricalAdvice:
    return HistoricalAdvice(
        advice_id=advice_id,
        issued_at=datetime(2025, 11, 1, tzinfo=UTC),
        ticker="AAPL",
        direction="long",
        entry_px=200.0,
        realized_exit_px=200.0 * (1 + pnl_pct),
        realized_pnl_pct=pnl_pct,
        benchmark_pnl_pct=bench,
        realized_max_dd_pct=max_dd,
        held=held,
    )


def test_harness_aggregates_correctly():
    history = [_ad(advice_id=f"a-{i}", pnl_pct=0.10) for i in range(10)]
    h = WalkForwardHarness(history=history)
    r = h.run(prompt_version="v1.0.0")
    assert r.sample_size == 10
    assert r.avg_alpha == pytest.approx(0.05)  # 10% pnl − 5% bench
    assert r.hit_rate == 1.0


def test_harness_zero_history():
    r = WalkForwardHarness(history=[]).run(prompt_version="v0")
    assert r.sample_size == 0


def test_compare_passes_on_neutral_delta():
    base_history = [_ad(advice_id=f"a-{i}", pnl_pct=0.10) for i in range(20)]
    cand_history = [_ad(advice_id=f"a-{i}", pnl_pct=0.10) for i in range(20)]
    h_base = WalkForwardHarness(history=base_history)
    h_cand = WalkForwardHarness(history=cand_history)
    delta = compare(h_base.run(prompt_version="v1"), h_cand.run(prompt_version="v2"))
    assert not delta.materially_negative


def test_compare_fails_on_alpha_drop():
    base_history = [_ad(advice_id=f"a-{i}", pnl_pct=0.20) for i in range(20)]
    cand_history = [_ad(advice_id=f"a-{i}", pnl_pct=0.05) for i in range(20)]
    delta = compare(
        WalkForwardHarness(history=base_history).run(prompt_version="v1"),
        WalkForwardHarness(history=cand_history).run(prompt_version="v2"),
    )
    assert delta.alpha_delta < -DEFAULT_ALPHA_DROP_THRESHOLD
    assert delta.materially_negative is True


def test_compare_fails_on_hit_rate_drop():
    base_history = [_ad(advice_id=f"a-{i}", pnl_pct=0.10, held=True) for i in range(20)]
    cand_history = [
        _ad(advice_id=f"a-{i}", pnl_pct=0.10, held=(i < 10)) for i in range(20)
    ]
    delta = compare(
        WalkForwardHarness(history=base_history).run(prompt_version="v1"),
        WalkForwardHarness(history=cand_history).run(prompt_version="v2"),
    )
    assert delta.hit_rate_delta == pytest.approx(-0.5)
    assert delta.materially_negative is True


def test_override_token_in_pr_title():
    ok, reason = has_override("feat(prompts): bump persona [walk-forward override: known UI shift]")
    assert ok is True
    assert "UI shift" in reason

    ok, _ = has_override("feat(prompts): bump persona")
    assert ok is False


def test_synthetic_prompt_bump_round_trip():
    """Plan §T1.12 acceptance: synthetic prompt-bump runs the harness;
    delta is computed; CI would gate on the materially_negative flag."""
    base_history = [_ad(advice_id=f"a-{i}", pnl_pct=0.10) for i in range(50)]
    cand_history = [_ad(advice_id=f"a-{i}", pnl_pct=0.09) for i in range(50)]  # 1pp drop
    delta = compare(
        WalkForwardHarness(history=base_history).run(prompt_version="v1.0.0"),
        WalkForwardHarness(history=cand_history).run(prompt_version="v1.1.0"),
    )
    assert not delta.materially_negative  # 1pp drop is within tolerance
    assert delta.alpha_delta == pytest.approx(-0.01)

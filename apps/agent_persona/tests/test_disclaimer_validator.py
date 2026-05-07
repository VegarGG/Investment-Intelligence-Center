"""Workflow 13 §2.4 + §5.5 — disclaimer is a hard rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import ulid
from persona.loader import load
from persona.output_validator import (
    DisclaimerMismatch,
    WrongAgent,
    validate,
)
from schema import AdviceV1, Asset, Evidence


def _advice(*, agent: str, disclaimer: str | None) -> AdviceV1:
    now = datetime.now(UTC)
    return AdviceV1(
        id=str(ulid.ULID()),
        agent=agent,
        issued_at=now,
        asset=Asset(
            kind="commodity" if False else "equity",  # type: ignore[arg-type]
            ticker="GLD",
            venue="NYSE",
        ),
        thesis="Stylized take.",
        direction="long",
        confidence=0.5,
        entry_band=(100.0, 101.0),
        target_band=(110.0, 115.0),
        stop_loss=95.0,
        horizon_days=180,
        max_drawdown_pct=10.0,
        sizing_hint_pct_nav=2.0,
        expires_at=now + timedelta(days=180),
        evidence=[Evidence(kind="news", ref="evt:1")],
        disclaimer=disclaimer,
    )


def test_correct_disclaimer_passes() -> None:
    spec = load("docs/prompts/persona/rogers.yaml")
    advice = _advice(agent="persona.rogers", disclaimer=spec.disclaimer)
    validate(advice, spec=spec)


def test_missing_disclaimer_rejected() -> None:
    _ = load("docs/prompts/persona/rogers.yaml")
    with pytest.raises(ValueError):
        # The schema-level validator already blocks blank disclaimers for personas.
        _advice(agent="persona.rogers", disclaimer=None)


def test_wrong_agent_rejected() -> None:
    spec = load("docs/prompts/persona/rogers.yaml")
    advice = _advice(agent="persona.buffett", disclaimer=spec.disclaimer)
    with pytest.raises(WrongAgent):
        validate(advice, spec=spec)


def test_disclaimer_mismatch_rejected() -> None:
    spec = load("docs/prompts/persona/rogers.yaml")
    advice = _advice(agent="persona.rogers", disclaimer="Some other disclaimer")
    with pytest.raises(DisclaimerMismatch):
        validate(advice, spec=spec)

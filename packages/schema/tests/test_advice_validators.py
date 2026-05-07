"""Workflow 05 §3 — every hard validator on AdviceV1 has at least one test.

Acceptance criterion §10: ≥15 validator cases.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from schema.advice import AdviceV1


def _build(good: dict[str, Any], **overrides: Any) -> AdviceV1:
    """Apply overrides via dotted-path style or top-level keys."""
    payload = {**good, **overrides}
    return AdviceV1.model_validate(payload)


class TestHappyPaths:
    def test_long_ok(self, good_long: dict[str, Any]) -> None:
        adv = AdviceV1.model_validate(good_long)
        assert adv.direction == "long"
        assert adv.entry_band == (89.0, 91.5)

    def test_short_ok(self, good_long: dict[str, Any]) -> None:
        adv = _build(
            good_long,
            direction="short",
            entry_band=[100.0, 102.0],
            target_band=[90.0, 95.0],
            stop_loss=104.0,
        )
        assert adv.direction == "short"

    def test_flat_ok(self, good_long: dict[str, Any]) -> None:
        adv = _build(
            good_long,
            direction="flat",
            entry_band=[100.0, 100.0],
            target_band=[100.0, 100.0],
            stop_loss=100.0,
            evidence=[],
        )
        assert adv.direction == "flat"


class TestIdValidator:
    def test_id_must_be_ulid(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="ULID"):
            _build(good_long, id="not-a-ulid")

    def test_id_must_be_26_chars(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="ULID"):
            _build(good_long, id="01HX8E5G7M0000")  # too short


class TestConfidence:
    def test_confidence_above_one_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            _build(good_long, confidence=1.5)

    def test_confidence_below_zero_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            _build(good_long, confidence=-0.1)


class TestBandOrdering:
    def test_entry_band_inverted_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="ascending"):
            _build(good_long, entry_band=[100.0, 80.0])

    def test_target_band_inverted_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="ascending"):
            _build(good_long, target_band=[110.0, 95.0])


class TestDirectionConsistency:
    def test_long_with_target_below_entry_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="long: entry_band"):
            _build(good_long, target_band=[80.0, 85.0])

    def test_long_with_stop_above_entry_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="long: stop_loss"):
            _build(good_long, stop_loss=92.0)

    def test_short_with_target_above_entry_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="short: target_band"):
            _build(
                good_long,
                direction="short",
                entry_band=[100.0, 102.0],
                target_band=[105.0, 110.0],  # wrong side
                stop_loss=104.0,
            )

    def test_short_with_stop_below_entry_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="short: stop_loss"):
            _build(
                good_long,
                direction="short",
                entry_band=[100.0, 102.0],
                target_band=[90.0, 95.0],
                stop_loss=99.0,  # below entry — wrong for short
            )

    def test_flat_with_unequal_bands_rejected(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="flat:"):
            _build(
                good_long,
                direction="flat",
                entry_band=[100.0, 101.0],
                target_band=[100.0, 100.0],
                stop_loss=100.0,
                evidence=[],
            )


class TestEvidenceRequirement:
    def test_directional_requires_evidence(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="evidence is required"):
            _build(good_long, evidence=[])

    def test_flat_allows_no_evidence(self, good_long: dict[str, Any]) -> None:
        adv = _build(
            good_long,
            direction="flat",
            entry_band=[100.0, 100.0],
            target_band=[100.0, 100.0],
            stop_loss=100.0,
            evidence=[],
        )
        assert adv.evidence == []


class TestExpiry:
    def test_expiry_before_issue_rejected(self, good_long: dict[str, Any]) -> None:
        good_long["expires_at"] = good_long["issued_at"]
        with pytest.raises(ValueError, match="must be after issued_at"):
            AdviceV1.model_validate(good_long)

    def test_expiry_more_than_one_year_rejected(self, good_long: dict[str, Any]) -> None:
        from datetime import datetime as _dt

        issued = _dt.fromisoformat(good_long["issued_at"])
        good_long["expires_at"] = (issued + timedelta(days=400)).isoformat()
        with pytest.raises(ValueError, match="<= 365"):
            AdviceV1.model_validate(good_long)


class TestPersonaDisclaimerInline:
    """Persona disclaimer rule is its own test_persona_disclaimer.py file too;
    one happy-path here keeps the validator-count count clean."""

    def test_persona_must_carry_disclaimer(self, good_long: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="disclaimer"):
            _build(good_long, agent="persona.rogers")

    def test_persona_with_disclaimer_ok(self, good_long: dict[str, Any]) -> None:
        adv = _build(
            good_long,
            agent="persona.rogers",
            disclaimer="Stylized agent inspired by public writings; not Mr. Rogers.",
        )
        assert adv.agent == "persona.rogers"

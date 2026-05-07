"""Workflow 05 §2 + §10 acceptance — every published subject must be `.v\\d+`."""

from __future__ import annotations

import pytest
from data_bus.exceptions import InvalidSubject
from data_bus.subjects import (
    ADVICE_FUNDAMENTAL,
    ADVICE_QUANT,
    BACKTEST_DAILY,
    BACKTEST_FILL,
    BACKTEST_LEADERBOARD,
    INTEL_BRIEF,
    INTEL_DASHBOARD,
    INTEL_DIGEST,
    KV_BUCKETS,
    OPS_ALERT,
    OPS_HEARTBEAT,
    SECRETARY_NOTIFY,
    STREAMS,
    advice_persona,
    assert_valid_subject,
    stream_for,
)


class TestSubjectGuard:
    @pytest.mark.parametrize(
        "subject",
        [
            INTEL_DIGEST,
            INTEL_DASHBOARD,
            INTEL_BRIEF,
            ADVICE_FUNDAMENTAL,
            ADVICE_QUANT,
            BACKTEST_FILL,
            BACKTEST_DAILY,
            BACKTEST_LEADERBOARD,
            SECRETARY_NOTIFY,
            OPS_HEARTBEAT,
            OPS_ALERT,
        ],
    )
    def test_canonical_subjects_pass(self, subject: str) -> None:
        assert_valid_subject(subject)

    @pytest.mark.parametrize("slug", ["rogers", "buffett", "soros", "degen"])
    def test_persona_slugs_yield_valid_subject(self, slug: str) -> None:
        subject = advice_persona(slug)
        assert_valid_subject(subject)
        assert subject == f"advice.persona.{slug}.v1"

    def test_persona_slug_alnum_required(self) -> None:
        with pytest.raises(InvalidSubject):
            advice_persona("bad slug")

    def test_uppercase_subject_rejected(self) -> None:
        with pytest.raises(InvalidSubject):
            assert_valid_subject("Intel.digest.v1")

    def test_subject_without_version_rejected(self) -> None:
        with pytest.raises(InvalidSubject):
            assert_valid_subject("advice.beta")

    def test_subject_with_alpha_version_rejected(self) -> None:
        with pytest.raises(InvalidSubject):
            assert_valid_subject("advice.fundamental.va")

    def test_subject_with_trailing_dot_rejected(self) -> None:
        with pytest.raises(InvalidSubject):
            assert_valid_subject("advice.fundamental.v1.")

    def test_empty_subject_rejected(self) -> None:
        with pytest.raises(InvalidSubject):
            assert_valid_subject("")


class TestStreamMapping:
    def test_intel_subject_maps_to_intel_stream(self) -> None:
        assert stream_for(INTEL_DIGEST) == "INTEL"

    def test_advice_subject_maps_to_advice_stream(self) -> None:
        assert stream_for(ADVICE_FUNDAMENTAL) == "ADVICE"
        assert stream_for(advice_persona("rogers")) == "ADVICE"

    def test_backtest_subject_maps_to_backtest_stream(self) -> None:
        assert stream_for(BACKTEST_FILL) == "BACKTEST"

    def test_secretary_maps_to_secretary_stream(self) -> None:
        assert stream_for(SECRETARY_NOTIFY) == "SECRETARY"

    def test_ops_maps_to_ops_stream(self) -> None:
        assert stream_for(OPS_HEARTBEAT) == "OPS"
        assert stream_for(OPS_ALERT) == "OPS"

    def test_unknown_subject_raises(self) -> None:
        with pytest.raises(InvalidSubject):
            stream_for("custom.thing.v1")

    def test_streams_table_has_all_five(self) -> None:
        names = {spec.name for spec in STREAMS}
        assert names == {"INTEL", "ADVICE", "BACKTEST", "SECRETARY", "OPS"}

    def test_advice_stream_is_forever(self) -> None:
        advice_spec = next(s for s in STREAMS if s.name == "ADVICE")
        assert advice_spec.retention_seconds is None

    def test_kv_buckets_match_ground_truth(self) -> None:
        assert KV_BUCKETS == ("iic_state", "iic_locks", "iic_versions")

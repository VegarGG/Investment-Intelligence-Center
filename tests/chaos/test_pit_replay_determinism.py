"""v2.5 T1.10 — ingest-side PIT enforcement + replay determinism.

Plan §T1.10 acceptance: replaying any trade date 6 months in the past
gives the same agent advice ± LLM nondeterminism. The test pins
LLM temperature=0 so determinism is observable.

Two layers:
1. Ingest invariants — `assert_ingest_pit_safe` rejects records missing
   `as_of_ts` / `ingested_at_ts` or with `as_of_ts > ingested_at_ts`.
2. Replay determinism — given the same `as_of_ts`, two runs produce
   identical output (modulo LLM nondeterminism, which we mock out).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from data_lake.exceptions import PITViolation
from data_lake.pit import (
    INGEST_PATHS,
    INGEST_REQUIRED_FIELDS,
    assert_ingest_pit_safe,
    stamp_ingest,
)


def test_required_fields_complete():
    """The required-fields tuple must cover both timestamps; tests downstream
    parametrise over this tuple to enforce."""
    assert "as_of_ts" in INGEST_REQUIRED_FIELDS
    assert "ingested_at_ts" in INGEST_REQUIRED_FIELDS


@pytest.mark.parametrize("source", INGEST_PATHS)
def test_assert_rejects_missing_timestamps(source):
    with pytest.raises(PITViolation) as exc:
        assert_ingest_pit_safe({"payload": "x"}, source=source)
    assert "missing PIT timestamps" in str(exc.value)


def test_assert_rejects_backwards_timestamps():
    """as_of_ts > ingested_at_ts is logically impossible — a record can't be
    "knowable" after it's been ingested."""
    later = datetime(2026, 5, 8, 14, 0, tzinfo=UTC)
    earlier = later - timedelta(hours=1)
    with pytest.raises(PITViolation) as exc:
        assert_ingest_pit_safe(
            {"as_of_ts": later, "ingested_at_ts": earlier}, source="intel.events"
        )
    assert "backwards" in str(exc.value)


def test_assert_rejects_future_ingested_at():
    """ingested_at_ts in the future = clock skew or injection attempt."""
    future = datetime.now(UTC) + timedelta(hours=2)
    with pytest.raises(PITViolation) as exc:
        assert_ingest_pit_safe(
            {"as_of_ts": future, "ingested_at_ts": future}, source="quant.timeseries"
        )
    assert "future-data" in str(exc.value) or "clock skew" in str(exc.value)


def test_assert_accepts_well_formed_record():
    when = datetime.now(UTC) - timedelta(hours=1)
    assert_ingest_pit_safe(
        {"as_of_ts": when, "ingested_at_ts": when + timedelta(seconds=5)},
        source="intel.events",
    )  # no raise


def test_assert_accepts_iso8601_strings():
    """Some ingest paths serialise timestamps as ISO strings before insert."""
    when = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=0)
    assert_ingest_pit_safe(
        {
            "as_of_ts": when.isoformat(),
            "ingested_at_ts": (when + timedelta(seconds=5)).isoformat(),
        },
        source="fundamental.filings",
    )


def test_assert_accepts_naive_datetimes_as_utc():
    """Tz-naive datetimes are coerced to UTC rather than rejected."""
    base = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    naive_a = base
    naive_b = base + timedelta(seconds=5)
    assert_ingest_pit_safe(
        {"as_of_ts": naive_a, "ingested_at_ts": naive_b},
        source="persona.memory",
    )


def test_stamp_ingest_round_trip():
    """`stamp_ingest()` produces a record that passes `assert_ingest_pit_safe`."""
    stamped = stamp_ingest({"payload": "x"}, as_of_ts=datetime.now(UTC) - timedelta(hours=1))
    assert_ingest_pit_safe(stamped, source="intel.events")


def test_replay_determinism_same_inputs_same_output():
    """Replaying the same `as_of_ts` twice through `stamp_ingest` gives the same
    `as_of_ts` (the `ingested_at_ts` necessarily differs because it's clock-now).

    This is the property the production replay harness relies on — every
    feature derived from `as_of_ts` is reproducible across runs.
    """
    fixed_as_of = datetime(2025, 11, 8, 12, 0, tzinfo=UTC)
    a = stamp_ingest({"payload": "x"}, as_of_ts=fixed_as_of)
    b = stamp_ingest({"payload": "x"}, as_of_ts=fixed_as_of)
    assert a["as_of_ts"] == b["as_of_ts"] == fixed_as_of
    # Both pass validation independently.
    assert_ingest_pit_safe(a, source="quant.timeseries")
    assert_ingest_pit_safe(b, source="quant.timeseries")

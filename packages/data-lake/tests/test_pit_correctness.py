"""Workflow 02 §6 — PIT correctness rules, unit-tested via sqlglot (no DB)."""

from __future__ import annotations

import pytest

from data_lake.exceptions import PITViolation
from data_lake.pit import assert_pit_safe


class TestAssertPITSafe:
    def test_passes_with_as_of_lte(self) -> None:
        assert_pit_safe(
            "SELECT * FROM lake.timeseries WHERE as_of <= '2024-06-01'"
        )

    def test_passes_with_as_of_lt(self) -> None:
        assert_pit_safe(
            "SELECT * FROM lake.timeseries WHERE symbol = 'AAPL' AND as_of < '2024-06-01'"
        )

    def test_passes_with_as_of_in_join(self) -> None:
        assert_pit_safe(
            """
            SELECT t.* FROM lake.timeseries t
            JOIN lake.universe_membership u
              ON u.ticker = t.symbol AND t.as_of <= u.in_to
            """
        )

    def test_fails_when_only_ts_predicate_present(self) -> None:
        with pytest.raises(PITViolation):
            assert_pit_safe(
                "SELECT * FROM lake.timeseries WHERE ts <= '2024-06-01'"
            )

    def test_fails_when_no_predicate_at_all(self) -> None:
        # raw select from a PIT table without any WHERE clause
        with pytest.raises(PITViolation):
            assert_pit_safe("SELECT * FROM lake.timeseries")

    def test_passes_when_query_does_not_touch_pit_table(self) -> None:
        # universe_membership and macro_releases are NOT pit-sensitive in this rule
        assert_pit_safe("SELECT * FROM lake.advice WHERE agent = 'fundamental'")
        assert_pit_safe("SELECT * FROM lake.macro_releases")

    def test_passes_when_as_of_in_between(self) -> None:
        assert_pit_safe(
            "SELECT * FROM lake.timeseries WHERE as_of BETWEEN '2024-01-01' AND '2024-06-01'"
        )

    def test_fails_when_as_of_appears_only_in_select_list(self) -> None:
        # Selecting as_of but not constraining it is still a violation.
        with pytest.raises(PITViolation):
            assert_pit_safe(
                "SELECT symbol, ts, as_of FROM lake.timeseries WHERE symbol = 'AAPL'"
            )

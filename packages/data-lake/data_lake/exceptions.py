"""Typed exceptions for the data_lake package (workflow 02 §8 typed-clients vibe-prompt)."""

from __future__ import annotations


class DataLakeError(Exception):
    """Base for every typed error raised by data_lake."""


class PITViolation(DataLakeError):
    """A query touches lake.timeseries (or any as_of-stamped table) without
    constraining as_of. Raised by data_lake.pit.assert_pit_safe."""


class AdviceLedgerError(DataLakeError):
    """A write to lake.advice failed structural validation before the DB even saw it."""


class BrokenChainError(AdviceLedgerError):
    """verify_chain detected a row whose row_hash does not match
    sha256(prev_hash || canonical_json(payload)). The advice ledger is
    tamper-evident; this should never happen in practice."""

    def __init__(self, agent: str, broken_at_id: str) -> None:
        self.agent = agent
        self.broken_at_id = broken_at_id
        super().__init__(f"chain broken for agent={agent} at id={broken_at_id}")


class StoreUnavailable(DataLakeError):
    """Health-check helper raised when a store fails to respond."""

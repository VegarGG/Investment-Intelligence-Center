"""Workflow 11 §7 — citation guard rejects bare numbers."""

from __future__ import annotations

import pytest
from fund.writer import CitationGuardError, guard_citations


def test_uncited_percent_rejected() -> None:
    with pytest.raises(CitationGuardError):
        guard_citations("Revenue grew 12% last year and the multiple looks rich.")


def test_uncited_multiple_rejected() -> None:
    with pytest.raises(CitationGuardError):
        guard_citations("INTC trades at 20x earnings vs sector 14x.")


def test_uncited_dollar_rejected() -> None:
    with pytest.raises(CitationGuardError):
        guard_citations("FCF generation of $5,000 per quarter looks resilient.")


def test_cited_thesis_passes() -> None:
    text = "INTC trades at 20x earnings [ref:filing] vs sector 14x [ref:digest]."
    guard_citations(text)


def test_qualitative_thesis_passes() -> None:
    guard_citations("Quality moat with patient capital flow.")

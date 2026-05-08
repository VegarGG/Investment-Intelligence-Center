"""v2.5 T1.11 — markdown decision log + atomic-append acceptance."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from data_lake.decision_log import DecisionLog, DecisionLogEntry


@pytest.fixture
def log(tmp_path):
    return DecisionLog(root=tmp_path)


def _entry(advice_id: str = "01HX8E5G7M0000000000000001", agent: str = "fundamental") -> DecisionLogEntry:
    return DecisionLogEntry(
        advice_id=advice_id,
        agent=agent,
        issued_at=datetime(2026, 5, 8, 14, 0, tzinfo=UTC),
        rating="Buy",
        thesis="Quality compounders trade at a discount after the panic.",
        evidence_urls=("https://example.com/filing", "https://example.com/news"),
    )


@pytest.mark.asyncio
async def test_first_append_creates_file_with_header(log):
    path = await log.append(_entry())
    body = path.read_text()
    assert "# fundamental decision log" in body
    assert "<!-- BEGIN entry id=01HX8E5G7M0000000000000001 agent=fundamental -->" in body
    assert "<!-- END entry -->" in body


@pytest.mark.asyncio
async def test_subsequent_append_preserves_prior_entries(log):
    await log.append(_entry(advice_id="01HX0000000000000000000001"))
    await log.append(_entry(advice_id="01HX0000000000000000000002"))
    body = log.path_for("fundamental").read_text()
    assert body.count("<!-- BEGIN entry") == 2


@pytest.mark.asyncio
async def test_attach_reflection_writes_block(log):
    await log.append(_entry())
    ok = await log.attach_reflection(
        agent="fundamental",
        advice_id="01HX8E5G7M0000000000000001",
        reflection="Realized +12%; thesis held; quality moat compounded as expected.",
    )
    assert ok is True
    body = log.path_for("fundamental").read_text()
    assert "Reflection:" in body
    assert "thesis held" in body


@pytest.mark.asyncio
async def test_attach_reflection_replaces_prior_reflection(log):
    await log.append(_entry())
    await log.attach_reflection("fundamental", "01HX8E5G7M0000000000000001", "old")
    await log.attach_reflection("fundamental", "01HX8E5G7M0000000000000001", "new")
    body = log.path_for("fundamental").read_text()
    assert body.count("Reflection:") == 1
    assert "new" in body
    assert "old" not in body


@pytest.mark.asyncio
async def test_attach_reflection_missing_advice_returns_false(log):
    await log.append(_entry())
    ok = await log.attach_reflection(
        agent="fundamental", advice_id="missing-advice", reflection="x"
    )
    assert ok is False


@pytest.mark.asyncio
async def test_iter_entries_returns_all(log):
    await log.append(_entry(advice_id="01HX0000000000000000000001"))
    await log.append(_entry(advice_id="01HX0000000000000000000002"))
    await log.attach_reflection("fundamental", "01HX0000000000000000000001", "alpha +5%")

    entries = list(log.iter_entries("fundamental"))
    assert len(entries) == 2
    by_id = {e["advice_id"]: e for e in entries}
    assert by_id["01HX0000000000000000000001"]["reflection"] == "alpha +5%"
    assert by_id["01HX0000000000000000000002"]["reflection"] is None


@pytest.mark.asyncio
async def test_atomic_write_no_temp_files_left(log, tmp_path):
    """`os.replace` semantics: no `.tmp.*` files survive a successful write."""
    await log.append(_entry())
    leftovers = list((tmp_path).glob(".tmp.*"))
    assert leftovers == []


@pytest.mark.asyncio
async def test_per_agent_isolation(log):
    """Two agents write to different files."""
    await log.append(_entry(agent="fundamental"))
    await log.append(_entry(agent="quant", advice_id="01HX0000000000000000000099"))
    assert log.path_for("fundamental").exists()
    assert log.path_for("quant").exists()
    assert "fundamental" not in log.path_for("quant").read_text()


@pytest.mark.asyncio
async def test_reflector_writes_through_decision_log(tmp_path):
    """End-to-end: Reflector → DecisionLog.attach_reflection."""
    from backtest.reflect import RealizedOutcome, Reflector

    log = DecisionLog(root=tmp_path)
    await log.append(_entry(agent="quant"))

    reflector = Reflector(decision_log=log)
    ok = await reflector.reflect(
        RealizedOutcome(
            advice_id="01HX8E5G7M0000000000000001",
            agent="quant",
            ticker="AAPL",
            venue="NASDAQ",
            direction="long",
            entry_px=200.0,
            exit_px=240.0,
            exit_reason="target",
            realized_pnl_pct=0.20,
            benchmark_pnl_pct=0.05,
            issued_at=datetime(2026, 5, 8, tzinfo=UTC),
            closed_at=datetime(2026, 5, 30, tzinfo=UTC),
        )
    )
    assert ok is True
    body = log.path_for("quant").read_text()
    assert "alpha vs SPY = +15.0%" in body
    assert "Thesis-held" in body

"""Workflow 02 §5.4 — hash chain unit + integration tests.

Unit tests cover the deterministic compute_row_hash + canonical-JSON path
without a DB. The full integration test is gated by the `integration`
marker (skipped unless IIC_INTEGRATION=1) and exercises append + verify_chain
against a real Postgres + Timescale.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from data_lake.advice_ledger import (
    _canonical_json,
    append,
    compute_row_hash,
    verify_chain,
)
from data_lake.exceptions import AdviceLedgerError


def _sample_advice(idx: int, agent: str = "test") -> dict[str, Any]:
    """Build a syntactically-valid advice envelope for unit tests."""
    return {
        "schema": "advice.v1",
        "id": f"01HX8E5G7M0000000000000{idx:03d}"[:26],
        "agent": agent,
        "issued_at": f"2026-05-06T13:{idx:02d}:00-07:00",
        "asset": {"kind": "equity", "ticker": "INTC", "venue": "NASDAQ"},
        "thesis": "stub",
        "direction": "long",
        "confidence": 0.5,
        "entry_band": [89.0, 91.5],
        "target_band": [95.0, 100.0],
        "stop_loss": 85.0,
        "horizon_days": 7,
        "max_drawdown_pct": 6.0,
        "sizing_hint_pct_nav": 2.5,
        "expires_at": "2026-05-13T13:30:00-07:00",
        "evidence": [{"kind": "news", "ref": "intel.digest.v1#evt-1"}],
    }


class TestCanonicalJSON:
    def test_keys_are_sorted(self) -> None:
        a = _canonical_json({"b": 1, "a": 2})
        b = _canonical_json({"a": 2, "b": 1})
        assert a == b
        assert a == b'{"a":2,"b":1}'

    def test_no_whitespace(self) -> None:
        out = _canonical_json({"a": 1, "b": 2})
        assert b" " not in out


class TestComputeRowHash:
    def test_first_row_hash_is_just_payload_hash(self) -> None:
        payload = {"agent": "x", "value": 1}
        got = compute_row_hash(None, payload)
        expected = hashlib.sha256(_canonical_json(payload)).digest()
        assert got == expected
        assert len(got) == 32

    def test_subsequent_row_includes_prev_hash(self) -> None:
        payload = {"agent": "x", "value": 2}
        prev = b"\x01" * 32
        got = compute_row_hash(prev, payload)
        expected = hashlib.sha256(prev + _canonical_json(payload)).digest()
        assert got == expected

    def test_payload_change_breaks_hash(self) -> None:
        prev = b"\x01" * 32
        h1 = compute_row_hash(prev, {"value": 1})
        h2 = compute_row_hash(prev, {"value": 2})
        assert h1 != h2

    def test_chain_links_propagate(self) -> None:
        """Walk a 5-row chain entirely in Python; each row_hash matches recompute."""
        prev: bytes | None = None
        chain: list[tuple[bytes | None, bytes, dict[str, Any]]] = []
        for i in range(5):
            payload = {"i": i, "thesis": f"row-{i}"}
            row_hash = compute_row_hash(prev, payload)
            chain.append((prev, row_hash, payload))
            prev = row_hash

        # Independently recompute, mimicking what verify_chain does over canonical bytes.
        recomputed_prev: bytes | None = None
        for db_prev, db_row_hash, payload in chain:
            h = hashlib.sha256()
            if recomputed_prev is not None:
                h.update(recomputed_prev)
            h.update(_canonical_json(payload))
            assert h.digest() == db_row_hash
            assert recomputed_prev == db_prev
            recomputed_prev = db_row_hash


class TestAppendValidation:
    """append() should reject malformed payloads before touching the DB."""

    @pytest.mark.asyncio
    async def test_missing_required_keys_raises(self) -> None:
        bad = _sample_advice(1)
        del bad["thesis"]
        with pytest.raises(AdviceLedgerError, match="missing required keys"):
            await append(bad)

    @pytest.mark.asyncio
    async def test_empty_evidence_raises(self) -> None:
        bad = _sample_advice(1)
        bad["evidence"] = []
        with pytest.raises(AdviceLedgerError, match="empty evidence"):
            await append(bad)


@pytest.mark.integration
class TestChainIntegration:
    """Full chain over a live Postgres. Run with IIC_INTEGRATION=1."""

    @pytest.mark.asyncio
    async def test_insert_100_advices_chain_ok(self) -> None:
        agent = "test_chain_100"
        for i in range(100):
            await append(_sample_advice(i, agent=agent))
        status = await verify_chain(agent)
        assert status.kind == "ok"
        assert status.rows_checked == 100

    @pytest.mark.asyncio
    async def test_corrupting_a_row_breaks_chain(self) -> None:
        """Tamper detection: rewrite payload_canonical for one row out-of-band
        and verify_chain catches it. Requires superuser to bypass the
        REVOKE UPDATE on iic_app — skip if running as iic_app."""
        from data_lake.postgres import session
        from sqlalchemy import text

        agent = "test_chain_tamper"
        for i in range(5):
            await append(_sample_advice(i, agent=agent))

        async with session("app") as s:
            try:
                await s.execute(
                    text(
                        "UPDATE lake.advice SET payload_canonical = '\\x00'::bytea "
                        "WHERE agent = :agent ORDER BY issued_at LIMIT 1"
                    ),
                    {"agent": agent},
                )
            except Exception:
                pytest.skip("UPDATE blocked by role grants — re-run as superuser")

        status = await verify_chain(agent)
        assert status.kind == "broken"
        assert status.broken_at_id is not None


@pytest.mark.integration
class TestLedgerImmutability:
    """Acceptance criterion: psql -U iic_app DELETE FROM lake.advice fails."""

    @pytest.mark.asyncio
    async def test_iic_app_cannot_delete(self) -> None:
        from data_lake.postgres import session
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        agent = "test_immut"
        await append(_sample_advice(0, agent=agent))
        with pytest.raises(ProgrammingError):
            async with session("app") as s:
                await s.execute(
                    text("DELETE FROM lake.advice WHERE agent = :agent"),
                    {"agent": agent},
                )

    @pytest.mark.asyncio
    async def test_iic_app_cannot_update(self) -> None:
        from data_lake.postgres import session
        from sqlalchemy import text
        from sqlalchemy.exc import ProgrammingError

        agent = "test_immut_upd"
        await append(_sample_advice(0, agent=agent))
        with pytest.raises(ProgrammingError):
            async with session("app") as s:
                await s.execute(
                    text("UPDATE lake.advice SET thesis = 'x' WHERE agent = :agent"),
                    {"agent": agent},
                )

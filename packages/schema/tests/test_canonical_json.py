"""Workflow 05 §11 — canonical_json determinism for hash chains."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel
from schema.canonical import canonical_json


class _Sample(BaseModel):
    b: int
    a: str
    issued_at: datetime


class TestCanonicalJSON:
    def test_keys_are_sorted(self) -> None:
        out = canonical_json({"b": 2, "a": 1})
        assert out == b'{"a":1,"b":2}'

    def test_no_whitespace(self) -> None:
        out = canonical_json({"a": 1, "b": 2})
        assert b" " not in out

    def test_pydantic_round_trip(self) -> None:
        m = _Sample(a="x", b=3, issued_at=datetime(2026, 5, 6, 13, 30, tzinfo=UTC))
        out = canonical_json(m)
        # keys sorted: a, b, issued_at
        assert out.startswith(b'{"a":"x"')
        assert b'"b":3' in out
        # datetime serialized to UTC Z
        assert b'"issued_at":"2026-05-06T13:30:00Z"' in out

    def test_byte_identical_across_dict_orderings(self) -> None:
        a = canonical_json({"a": 1, "b": 2, "c": 3})
        b = canonical_json({"c": 3, "a": 1, "b": 2})
        assert a == b

    def test_float_precision_preserved(self) -> None:
        # The hash chain depends on byte-stable float reps.
        out = canonical_json({"x": 1.234567890123})
        # orjson defaults to ~15-digit precision — fine for our use.
        assert b"1.234567890123" in out

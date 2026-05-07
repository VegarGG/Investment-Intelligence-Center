"""Workflow 15 §2.5 — slash command catalog."""

from __future__ import annotations

import pytest
from secretary.inbound.slash_commands import (
    KNOWN_COMMANDS,
    UnknownSlash,
    dispatch,
    parse_slash,
)


def test_parse_known_commands() -> None:
    for cmd in KNOWN_COMMANDS:
        parsed_cmd, _ = parse_slash(f"/{cmd}")
        assert parsed_cmd == cmd


def test_unknown_slash_raises() -> None:
    with pytest.raises(UnknownSlash):
        parse_slash("/notarealcommand")


def test_dispatch_explain_returns_body() -> None:
    out = dispatch("/explain 01HXABC")
    assert "01HXABC" in out.body


def test_dispatch_help_lists_commands() -> None:
    out = dispatch("/help")
    for cmd in KNOWN_COMMANDS:
        assert f"/{cmd}" in out.body


def test_non_slash_rejected() -> None:
    with pytest.raises(ValueError):
        parse_slash("hello world")

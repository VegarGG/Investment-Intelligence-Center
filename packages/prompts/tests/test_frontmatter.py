"""Workflow 04 §6.1 — frontmatter parsing + validation."""

from __future__ import annotations

import pytest
from prompts.exceptions import FrontmatterError
from prompts.frontmatter import parse_text

GOOD = """---
caller_id: intel.synth
version: 1.0.0
tier: pro
status: stable
description: test
variables:
  - name: x
    type: string
    required: true
---
hello {{ x }}
"""


def test_parses_valid_prompt() -> None:
    parsed = parse_text(GOOD)
    assert parsed.frontmatter.caller_id == "intel.synth"
    assert parsed.frontmatter.version == "1.0.0"
    assert parsed.frontmatter.tier == "pro"
    assert parsed.body.strip() == "hello {{ x }}"
    assert parsed.frontmatter.variables[0].name == "x"


def test_missing_leading_delim_raises() -> None:
    with pytest.raises(FrontmatterError, match="missing leading"):
        parse_text("caller_id: intel.synth\n---\nbody")


def test_missing_closing_delim_raises() -> None:
    with pytest.raises(FrontmatterError, match="missing closing"):
        parse_text("---\ncaller_id: intel.synth\n")


def test_invalid_tier_raises() -> None:
    bad = "---\ncaller_id: x\nversion: 1.0.0\ntier: super_pro\n---\nbody"
    with pytest.raises(FrontmatterError):
        parse_text(bad)


def test_unknown_status_raises() -> None:
    bad = "---\ncaller_id: x\nversion: 1.0.0\ntier: pro\nstatus: maybe\n---\nbody"
    with pytest.raises(FrontmatterError):
        parse_text(bad)


def test_default_status_is_stable() -> None:
    minimal = "---\ncaller_id: x\nversion: 1.0.0\ntier: pro\n---\nbody"
    parsed = parse_text(minimal)
    assert parsed.frontmatter.status == "stable"

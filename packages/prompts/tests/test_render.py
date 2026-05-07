"""Workflow 04 §6.1 + §3 — render + variable validation + system/user split."""

from __future__ import annotations

import pytest
from prompts.exceptions import MissingVariableError
from prompts.frontmatter import Frontmatter, VariableSpec, parse_text
from prompts.render import merge_with_defaults, render_body, split_system_user


class TestMergeDefaults:
    def test_required_passthrough(self) -> None:
        spec = [VariableSpec(name="x", required=True)]
        out = merge_with_defaults(spec, {"x": "hi"})
        assert out["x"] == "hi"

    def test_missing_required_raises(self) -> None:
        spec = [VariableSpec(name="x", required=True)]
        with pytest.raises(MissingVariableError, match="required variable 'x'"):
            merge_with_defaults(spec, {})

    def test_optional_default_filled(self) -> None:
        spec = [VariableSpec(name="x", required=False, default="fallback")]
        out = merge_with_defaults(spec, {})
        assert out["x"] == "fallback"

    def test_extras_pass_through(self) -> None:
        spec = [VariableSpec(name="x", required=True)]
        out = merge_with_defaults(spec, {"x": "1", "y": "2"})
        assert out == {"x": "1", "y": "2"}


class TestRender:
    def test_substitution(self) -> None:
        assert render_body("hello {{ name }}", {"name": "world"}) == "hello world"

    def test_undefined_variable_raises(self) -> None:
        with pytest.raises(MissingVariableError):
            render_body("hello {{ name }}", {})

    def test_jinja_conditional(self) -> None:
        body = "{% if x %}yes{% else %}no{% endif %}"
        assert render_body(body, {"x": True}) == "yes"
        assert render_body(body, {"x": False}) == "no"


class TestSystemUserSplit:
    def test_no_system_role_returns_full_body(self) -> None:
        fm = Frontmatter(caller_id="x", version="1.0.0", tier="pro")
        sys, user = split_system_user("body text only", fm)
        assert sys is None
        assert user == "body text only"

    def test_first_paragraph_lifted_as_system(self) -> None:
        fm = Frontmatter(caller_id="x", version="1.0.0", tier="pro", system_role="first_paragraph")
        rendered = "You are a helpful assistant.\n\nHere's the user payload."
        sys, user = split_system_user(rendered, fm)
        assert sys == "You are a helpful assistant."
        assert user == "Here's the user payload."


class TestEndToEndFromFrontmatter:
    def test_parse_then_render(self) -> None:
        text = """---
caller_id: x
version: 1.0.0
tier: flash
variables:
  - name: name
    required: true
---
hello {{ name }}
"""
        parsed = parse_text(text)
        rendered = render_body(parsed.body, {"name": "ziwei"})
        assert rendered.strip() == "hello ziwei"

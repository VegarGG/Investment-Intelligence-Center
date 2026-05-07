"""Jinja2-style variable substitution with strict undefined-variable failure
(workflow 04 §6.1).
"""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateError

from .exceptions import MissingVariableError
from .frontmatter import Frontmatter, VariableSpec

_env = Environment(
    undefined=StrictUndefined,
    autoescape=False,  # noqa: S701 — prompts go to LLMs, not browsers; HTML escaping would corrupt JSON variables
    keep_trailing_newline=True,
)


def render_body(body: str, variables: dict[str, Any]) -> str:
    try:
        return _env.from_string(body).render(**variables)
    except TemplateError as exc:
        raise MissingVariableError(f"render failed: {exc}") from exc


def merge_with_defaults(declared: list[VariableSpec], passed: dict[str, Any]) -> dict[str, Any]:
    """Validate that every required variable was passed; fill defaults for the rest."""
    out: dict[str, Any] = {}
    for spec in declared:
        if spec.name in passed:
            out[spec.name] = passed[spec.name]
        elif spec.required and spec.default is None:
            raise MissingVariableError(f"required variable '{spec.name}' not supplied")
        else:
            out[spec.name] = spec.default
    # Pass-through extras (caller may supply variables the prompt doesn't declare;
    # Jinja's StrictUndefined will catch typos at render time anyway).
    for key, val in passed.items():
        out.setdefault(key, val)
    return out


def split_system_user(rendered: str, frontmatter: Frontmatter) -> tuple[str | None, str]:
    """If the frontmatter declares system_role: 'first_paragraph', lift the first
    paragraph as the system message; otherwise return (None, full_body)."""
    if frontmatter.system_role != "first_paragraph":
        return None, rendered
    parts = rendered.split("\n\n", 1)
    if len(parts) == 1:
        return parts[0].strip(), ""
    return parts[0].strip(), parts[1].lstrip("\n")

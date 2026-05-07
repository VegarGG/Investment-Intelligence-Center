"""Parses the YAML frontmatter block at the top of every prompt file.

GROUND TRUTH (workflow 04 §2.2): a prompt is a Markdown file whose first
non-empty content is a YAML block delimited by `---` ... `---`. The body
follows immediately after the closing delimiter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from .exceptions import FrontmatterError

Tier = Literal["flash", "pro", "embed"]
Status = Literal["stable", "beta", "deprecated"]


class VariableSpec(BaseModel):
    """One declared variable in the prompt's frontmatter `variables:` block."""

    name: str
    type: Literal["string", "int", "float", "bool", "json"] = "string"
    required: bool = True
    default: Any | None = None


class Frontmatter(BaseModel):
    caller_id: str
    version: str
    tier: Tier
    description: str = ""
    status: Status = "stable"
    variables: list[VariableSpec] = Field(default_factory=list)
    expected_output_schema: str | None = None
    system_role: str | None = None  # optional: lift first paragraph as system message


class ParsedPrompt(BaseModel):
    frontmatter: Frontmatter
    body: str
    source_path: Path

    model_config = {"arbitrary_types_allowed": True}


_DELIM = "---"


def parse_text(text: str, source_path: Path | None = None) -> ParsedPrompt:
    """Split YAML frontmatter from body and validate via Pydantic."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != _DELIM:
        raise FrontmatterError(
            f"prompt {source_path or '<inline>'} missing leading '---' frontmatter delimiter"
        )

    end_idx: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == _DELIM:
            end_idx = i
            break
    if end_idx is None:
        raise FrontmatterError(
            f"prompt {source_path or '<inline>'} missing closing '---' delimiter"
        )

    yaml_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")

    try:
        data = yaml.safe_load(yaml_text) or {}
        frontmatter = Frontmatter.model_validate(data)
    except (yaml.YAMLError, ValidationError) as exc:
        raise FrontmatterError(
            f"frontmatter validation failed in {source_path or '<inline>'}: {exc}"
        ) from exc

    return ParsedPrompt(
        frontmatter=frontmatter,
        body=body,
        source_path=source_path or Path("<inline>"),
    )


def parse_file(path: Path) -> ParsedPrompt:
    return parse_text(path.read_text(encoding="utf-8"), source_path=path)

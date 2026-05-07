"""Public surface — `get(caller_id, version=None, **vars) -> RenderedPrompt`
(workflow 04 §3, §6.2).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from packaging.version import Version
from pydantic import BaseModel

from .exceptions import (
    NoStableVersionError,
    UnknownCallerError,
)
from .frontmatter import ParsedPrompt, Tier, parse_file
from .publisher import persist
from .render import merge_with_defaults, render_body, split_system_user

REGISTRY_ROOT = Path(__file__).resolve().parent.parent / "registry"


class RenderedPrompt(BaseModel):
    caller_id: str
    version: str
    tier: Tier
    system: str | None
    user: str
    raw_template_path: str


@lru_cache(maxsize=512)
def _list_versions(caller_id: str) -> tuple[ParsedPrompt, ...]:
    """All parsed prompts for `caller_id`, sorted ascending by SemVer."""
    caller_dir = REGISTRY_ROOT / caller_id
    if not caller_dir.exists():
        raise UnknownCallerError(
            f"no registry directory for caller_id='{caller_id}' (looked in {caller_dir})"
        )
    parsed: list[ParsedPrompt] = []
    for path in sorted(caller_dir.glob("*.md")):
        parsed.append(parse_file(path))

    parsed.sort(key=lambda p: Version(p.frontmatter.version))
    return tuple(parsed)


def _pick_stable(parsed: tuple[ParsedPrompt, ...], caller_id: str) -> ParsedPrompt:
    stable = [p for p in parsed if p.frontmatter.status == "stable"]
    if not stable:
        raise NoStableVersionError(
            f"no stable version for caller_id='{caller_id}' "
            f"(found: {[p.frontmatter.version for p in parsed]})"
        )
    return max(stable, key=lambda p: Version(p.frontmatter.version))


def _pick_explicit(parsed: tuple[ParsedPrompt, ...], caller_id: str, version: str) -> ParsedPrompt:
    for p in parsed:
        if p.frontmatter.version == version:
            return p
    raise UnknownCallerError(
        f"caller_id='{caller_id}' has no version '{version}' "
        f"(available: {[p.frontmatter.version for p in parsed]})"
    )


def get(
    caller_id: str,
    *,
    version: str | None = None,
    **variables: Any,
) -> RenderedPrompt:
    """Resolve, render, and persist a prompt.

    Selection rule (§2.5):
      version=None → highest version with status=stable
      version=...  → exact match (lets agents address beta versions)
    """
    parsed_versions = _list_versions(caller_id)
    parsed = (
        _pick_explicit(parsed_versions, caller_id, version)
        if version is not None
        else _pick_stable(parsed_versions, caller_id)
    )

    fm = parsed.frontmatter
    final_vars = merge_with_defaults(fm.variables, variables)
    rendered_body = render_body(parsed.body, final_vars)
    system, user = split_system_user(rendered_body, fm)

    # Append-only publish — raises ImmutablePromptError if a previously-
    # published version's source has been mutated without a bump.
    source_text = parsed.source_path.read_text(encoding="utf-8")
    persist(fm.caller_id, fm.version, source_text)

    return RenderedPrompt(
        caller_id=fm.caller_id,
        version=fm.version,
        tier=fm.tier,
        system=system,
        user=user,
        raw_template_path=str(parsed.source_path),
    )


def list_callers() -> list[str]:
    """All caller_ids that have a registry directory."""
    if not REGISTRY_ROOT.exists():
        return []
    return sorted(p.name for p in REGISTRY_ROOT.iterdir() if p.is_dir())


def clear_cache() -> None:
    """Drop the lru_cache — used by tests that mutate registry files in-process."""
    _list_versions.cache_clear()

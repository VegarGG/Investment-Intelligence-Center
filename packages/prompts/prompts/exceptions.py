"""Typed exceptions for the prompt registry (workflow 04 §6, §8)."""

from __future__ import annotations


class PromptRegistryError(Exception):
    """Base for every typed error raised by the prompts package."""


class UnknownCallerError(PromptRegistryError):
    """No registry directory exists for the requested caller_id."""


class NoStableVersionError(PromptRegistryError):
    """The caller's directory has no version with status: stable."""


class FrontmatterError(PromptRegistryError):
    """The YAML frontmatter is malformed or fails Pydantic validation."""


class MissingVariableError(PromptRegistryError):
    """A required variable from the frontmatter wasn't passed to get()."""


class ImmutablePromptError(PromptRegistryError):
    """A prompt file's content changed without the version being bumped.
    Workflow 04 §6.7 / §2.4 / acceptance criterion 3."""


class GoldenSetCoverageError(PromptRegistryError):
    """Eval golden set has < 3 entries for an active caller, or < 60 total."""

"""IIC prompts package — Versioned prompt registry + eval golden set (workflow 04)."""

from .exceptions import (
    FrontmatterError,
    GoldenSetCoverageError,
    ImmutablePromptError,
    MissingVariableError,
    NoStableVersionError,
    PromptRegistryError,
    UnknownCallerError,
)
from .registry import RenderedPrompt, get, list_callers

__version__ = "0.1.0"
__all__ = [
    "RenderedPrompt",
    "get",
    "list_callers",
    "PromptRegistryError",
    "UnknownCallerError",
    "NoStableVersionError",
    "FrontmatterError",
    "MissingVariableError",
    "ImmutablePromptError",
    "GoldenSetCoverageError",
]

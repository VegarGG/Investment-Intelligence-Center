"""Macro pull adapters (workflow 10 §5.6). Each release source plugs in via
`MacroSource.fetch(asof) -> list[MacroRelease]` so the synth step can pass
a uniform list to the LLM."""

from .protocol import InMemoryMacroSource, MacroRelease, MacroSource

__all__ = ["InMemoryMacroSource", "MacroRelease", "MacroSource"]

"""Inbound chat + WeCom callback (workflow 15 §5.3 - §5.5)."""

from .disagreement import render_disagreement_table
from .slash_commands import SlashResult, dispatch, parse_slash

__all__ = ["SlashResult", "dispatch", "parse_slash", "render_disagreement_table"]

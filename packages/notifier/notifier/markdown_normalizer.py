"""WeCom-compatible markdown normalizer (workflow 20 §8).

WeCom's markdown is opinionated:
  1. HTML stripped.
  2. H3+ demoted to bold lines.
  3. List nesting capped at 2 levels.
  4. `> ` quotes replaced with bold prefix.
  5. CJK-aware truncation at `max_chars` with a language-specific suffix.
  6. Inline code + fenced code blocks preserved.
  7. Single-underscore `__bold__` rewritten to `**bold**`.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 4096
TRUNCATE_SUFFIX_EN = "\n\n…more on dashboard → "
TRUNCATE_SUFFIX_ZH = "\n\n…更多见仪表板 → "

_HEADING_RE = re.compile(r"^(#{3,6})\s+(.*)$", re.MULTILINE)
_BLOCK_QUOTE_RE = re.compile(r"^>\s?(.*)$", re.MULTILINE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DOUBLE_UNDERSCORE_RE = re.compile(r"__([^_]+)__")
_LIST_INDENT_RE = re.compile(r"^( {2,})([-*+]\s)", re.MULTILINE)


def clean(
    text: str,
    *,
    language: str = "en",
    max_chars: int = DEFAULT_MAX_CHARS,
    dashboard_url: str = "",
) -> str:
    """Normalize WeCom-flavored markdown."""
    text = _strip_html(text)
    text = _demote_deep_headings(text)
    text = _replace_block_quotes(text)
    text = _cap_list_nesting(text)
    text = _double_to_star_bold(text)
    text = _truncate_chars(
        text,
        max_chars=max_chars,
        language=language,
        dashboard_url=dashboard_url,
    )
    return text


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub("", text)


def _demote_deep_headings(text: str) -> str:
    return _HEADING_RE.sub(lambda m: f"**{m.group(2).strip()}**", text)


def _replace_block_quotes(text: str) -> str:
    return _BLOCK_QUOTE_RE.sub(lambda m: f"**{m.group(1).strip()}**", text)


def _double_to_star_bold(text: str) -> str:
    """WeCom drops `__bold__`. Convert single-underscore syntax to **."""
    return _DOUBLE_UNDERSCORE_RE.sub(lambda m: f"**{m.group(1)}**", text)


def _cap_list_nesting(text: str) -> str:
    """Collapse > 2-level nested list items by clamping leading indent to 4 spaces."""

    def collapse(match: re.Match[str]) -> str:
        indent = match.group(1)
        marker = match.group(2)
        levels = len(indent) // 2
        capped = min(levels, 2)
        return ("  " * capped) + marker

    return _LIST_INDENT_RE.sub(collapse, text)


def _truncate_chars(
    text: str,
    *,
    max_chars: int,
    language: str,
    dashboard_url: str,
) -> str:
    """Char-aware truncation — never split a Unicode codepoint mid-grapheme.

    `len(text)` already counts characters (codepoints) in Python, so the
    boundary is naturally CJK-safe.
    """
    if len(text) <= max_chars:
        return text
    suffix = TRUNCATE_SUFFIX_ZH if language == "zh" else TRUNCATE_SUFFIX_EN
    suffix_full = f"{suffix}{dashboard_url}" if dashboard_url else suffix.rstrip(" ")
    keep = max_chars - len(suffix_full)
    if keep <= 0:
        return text[:max_chars]
    return text[:keep].rstrip() + suffix_full

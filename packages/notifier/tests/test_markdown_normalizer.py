"""Workflow 20 §8 — markdown normalizer (WeCom-flavored)."""

from __future__ import annotations

from notifier.markdown_normalizer import DEFAULT_MAX_CHARS, clean


def test_strips_html_tags() -> None:
    out = clean("<b>hello</b> <span style='x'>world</span>")
    assert "<" not in out and ">" not in out
    assert "hello" in out and "world" in out


def test_demotes_h3_and_deeper() -> None:
    out = clean("### deep\n#### deeper")
    assert "###" not in out
    assert "**deep**" in out
    assert "**deeper**" in out


def test_h1_h2_preserved() -> None:
    out = clean("# top\n## second")
    assert "# top" in out
    assert "## second" in out


def test_block_quote_replaced_with_bold() -> None:
    out = clean("> wisdom here")
    assert "> " not in out
    assert "**wisdom here**" in out


def test_double_underscore_bold_normalized() -> None:
    out = clean("This is __bold__ text.")
    assert "__bold__" not in out
    assert "**bold**" in out


def test_truncates_long_text_cjk_safe() -> None:
    text = "中文字符" * 2000  # > 4096 chars
    out = clean(text, language="zh", max_chars=DEFAULT_MAX_CHARS)
    assert len(out) <= DEFAULT_MAX_CHARS
    assert "更多见仪表板" in out
    # Verify no codepoint was sliced — every character round-trips.
    out.encode("utf-8")


def test_short_text_not_truncated() -> None:
    text = "hello world"
    assert clean(text) == "hello world"


def test_truncate_appends_dashboard_url_when_present() -> None:
    text = "x" * 5000
    out = clean(text, language="en", max_chars=200, dashboard_url="https://iic/d")
    assert "https://iic/d" in out
    assert len(out) <= 200


def test_list_nesting_capped_at_two_levels() -> None:
    text = "- a\n  - b\n    - c\n      - d"
    out = clean(text)
    # The deepest line had 6 leading spaces (3 levels); should collapse to 2.
    assert "      -" not in out

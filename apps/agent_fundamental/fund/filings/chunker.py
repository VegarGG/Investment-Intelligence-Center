"""Hierarchical chunker (workflow 11 §5.1).

First-pass split by Item heading (10-K Items 1, 1A, 7, 7A, 8); within an
Item, by sentence with a configurable token overlap. Token counting uses
a cheap whitespace approximation — tiktoken can be plugged in later.
"""

from __future__ import annotations

import re

from ..types import Chunk, Filing

ITEM_RE = re.compile(r"(?im)^\s*Item\s+([0-9A-Z]+)[\.:]?\s*(.*)$")
SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
DEFAULT_TOKEN_TARGET = 1000
DEFAULT_OVERLAP = 200


def split(
    filing: Filing,
    *,
    target_tokens: int = DEFAULT_TOKEN_TARGET,
    overlap_tokens: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    sections = _split_by_item(filing.text)
    out: list[Chunk] = []
    idx = 0
    for section_id, body in sections:
        for chunk_text in _chunk_section(body, target_tokens, overlap_tokens):
            out.append(
                Chunk(
                    parent_doc=filing.accession,
                    section=section_id,
                    chunk_idx=idx,
                    text=chunk_text,
                    token_count=_approx_tokens(chunk_text),
                )
            )
            idx += 1
    return out


def _split_by_item(text: str) -> list[tuple[str, str]]:
    """Group lines under their nearest preceding `Item N.` heading."""
    matches = list(ITEM_RE.finditer(text))
    if not matches:
        return [("body", text)]
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        section_id = f"Item {m.group(1)}"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((section_id, text[start:end].strip()))
    return out


def _chunk_section(body: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    if not body.strip():
        return []
    sentences = SENT_RE.split(body)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sent in sentences:
        st = _approx_tokens(sent)
        if current_tokens + st > target_tokens and current:
            chunks.append(" ".join(current).strip())
            tail = _tail_with_overlap(current, overlap_tokens)
            current = list(tail)
            current_tokens = sum(_approx_tokens(s) for s in current)
        current.append(sent)
        current_tokens += st
    if current:
        chunks.append(" ".join(current).strip())
    return [c for c in chunks if c]


def _tail_with_overlap(sentences: list[str], overlap_tokens: int) -> list[str]:
    out: list[str] = []
    total = 0
    for sent in reversed(sentences):
        st = _approx_tokens(sent)
        if total + st > overlap_tokens:
            break
        out.insert(0, sent)
        total += st
    return out


def _approx_tokens(text: str) -> int:
    """Whitespace count + 30% slack — close enough for chunk sizing."""
    return int(len(text.split()) * 1.3) + 1

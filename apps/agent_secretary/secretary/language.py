"""Language detection (workflow 15 §2.3).

Lightweight CJK-character ratio — full langdetect is unnecessary for
the EN/ZH choice the secretary actually makes.
"""

from __future__ import annotations

from typing import Literal

Language = Literal["en", "zh"]

CJK_RANGES = (
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x20000, 0x2A6DF),
)


def detect(text: str, *, default: Language = "en") -> Language:
    if not text:
        return default
    cjk = 0
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        ord_ch = ord(ch)
        if any(lo <= ord_ch <= hi for lo, hi in CJK_RANGES):
            cjk += 1
    if total == 0:
        return default
    return "zh" if cjk / total > 0.3 else "en"

"""Tone modes (workflow 15 §2.2).

`terse` for the principal, `conversational` default, `educational` for family.
"""

from __future__ import annotations

from typing import Literal

Tone = Literal["terse", "conv", "edu"]

TONE_SUFFIXES: dict[Tone, str] = {
    "terse": (
        "Be terse. Numbers first. No analogies, no hedging, no greetings. " "Avoid adjectives."
    ),
    "conv": (
        "Plain language. Conversational, light explanations. "
        "Avoid jargon unless the reader uses it."
    ),
    "edu": (
        "Explain to a family member with no finance background. "
        "Use analogies. No acronyms. Spell out company names instead of tickers."
    ),
}


def suffix(tone: Tone) -> str:
    return TONE_SUFFIXES[tone]

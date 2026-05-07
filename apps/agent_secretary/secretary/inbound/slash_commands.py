"""Slash command catalog (workflow 15 §2.5)."""

from __future__ import annotations

from dataclasses import dataclass

KNOWN_COMMANDS = (
    "leaderboard",
    "explain",
    "why",
    "disagree",
    "quiet",
    "tone",
    "help",
)


@dataclass(slots=True)
class SlashResult:
    command: str
    args: tuple[str, ...]
    body: str


class UnknownSlash(ValueError):
    """The user invoked an unregistered slash command."""


def parse_slash(text: str) -> tuple[str, tuple[str, ...]]:
    if not text.startswith("/"):
        raise ValueError("not a slash command")
    parts = text[1:].split()
    if not parts:
        raise ValueError("empty slash command")
    cmd = parts[0]
    if cmd not in KNOWN_COMMANDS:
        raise UnknownSlash(cmd)
    return cmd, tuple(parts[1:])


def dispatch(text: str) -> SlashResult:
    """Synchronous dispatcher — produces a markdown body. Real ops calls
    fan into the proper async handlers (leaderboard fetch, etc.)."""
    cmd, args = parse_slash(text)
    body = _render(cmd, args)
    return SlashResult(command=cmd, args=args, body=body)


def _render(cmd: str, args: tuple[str, ...]) -> str:
    if cmd == "help":
        return _help()
    if cmd == "leaderboard":
        return "Latest leaderboard:\n_(populated when backtester emits)_"
    if cmd == "explain":
        ref = args[0] if args else "(missing advice id)"
        return f"Explain mode for {ref}: deep-explain plan queued."
    if cmd == "why":
        ticker = args[0] if args else "(missing ticker)"
        return f"Open advices for {ticker}: pending lake.advice query."
    if cmd == "disagree":
        ticker = args[0] if args else "(missing ticker)"
        return f"Disagreement table for {ticker}: rendering pending advice scan."
    if cmd == "quiet":
        minutes = args[0] if args else "30"
        return f"Outbound non-critical pushes muted for {minutes} minutes."
    if cmd == "tone":
        tone = args[0] if args else "conv"
        return f"Tone set to `{tone}` for this conversation."
    return "(no-op)"


def _help() -> str:
    return (
        "Available commands:\n"
        "- `/leaderboard` — latest leaderboard\n"
        "- `/explain <advice_id>` — deep-explain on one advice\n"
        "- `/why <ticker>` — all open advices for ticker\n"
        "- `/disagree <ticker>` — render the agent-disagreement table\n"
        "- `/quiet <minutes>` — mute non-critical pushes\n"
        "- `/tone <terse|conv|edu>` — set conversation tone\n"
        "- `/help` — show this list"
    )

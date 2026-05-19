"""Conversational planner for the secretary's /chat endpoint (P6.2).

Wraps an LLM call ("secretary.plan" caller) that takes a natural-language
request and returns a structured list of RPCs to fan out across agents.

Output format the prompt asks for (also enforced as a JSON-mode response):

    [
      {"caller": "agent_intelligence", "endpoint": "/run/context", "args": {"ticker": "AAPL"}},
      {"caller": "agent_persona",      "endpoint": "/run/rerun",   "args": {"slug": "buffett"}}
    ]

The planner is **defensive** by design:

  - If JSON parsing fails, fall back to a single-step plan that hands the
    raw user text to `agent_secretary.brief.midday` so the user gets *some*
    answer rather than an error.
  - If the LLM emits an unknown caller, drop that step but keep the rest;
    log the drop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from llm_client import ChatMessage
from llm_client.router import chat_or_raise

log = logging.getLogger(__name__)

ALLOWED_CALLERS = (
    "agent_intelligence",
    "agent_fundamental",
    "agent_quant",
    "agent_persona",
    "agent_backtest",
    "agent_board",
    "orchestrator",
)


@dataclass(frozen=True, slots=True)
class PlanStep:
    caller: str
    endpoint: str
    args: dict[str, Any] = field(default_factory=dict)


PLANNER_SYSTEM = (
    "You are the IIC secretary's conversational planner. Given a user "
    "request and conversation context, output STRICTLY a JSON array of "
    "agent RPCs needed to satisfy the request. Each element is an object "
    "with `caller` (one of: "
    + ", ".join(ALLOWED_CALLERS)
    + "), `endpoint` (an existing path on that agent), and `args` "
    "(an object). Do not include explanations, only the JSON array. "
    "If the user is making small talk and no RPC is needed, return []."
)


def _parse_steps(raw_text: str) -> list[PlanStep]:
    text = raw_text.strip()
    if text.startswith("```"):
        # tolerate fenced code blocks the LLM sometimes adds
        text = text.split("```", 2)[1].split("```", 1)[0]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("planner: JSON parse failed (%s); falling back", exc)
        return []
    if not isinstance(data, list):
        log.warning("planner: top-level not array; ignoring")
        return []
    out: list[PlanStep] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        caller = item.get("caller")
        endpoint = item.get("endpoint")
        if caller not in ALLOWED_CALLERS or not isinstance(endpoint, str):
            log.warning("planner: dropping bad step %s", item)
            continue
        args = item.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        out.append(PlanStep(caller=caller, endpoint=endpoint, args=args))
    return out


async def plan(text: str, *, context_turns: list[dict[str, str]] | None = None) -> list[PlanStep]:
    """Ask the planner LLM to translate text into a sequence of agent RPCs."""
    messages = [ChatMessage(role="system", content=PLANNER_SYSTEM)]
    for turn in context_turns or []:
        role = str(turn.get("role", "user"))
        if role not in ("user", "assistant", "system"):
            continue
        messages.append(ChatMessage(role=role, content=str(turn.get("content", ""))))  # type: ignore[arg-type]
    messages.append(ChatMessage(role="user", content=text))
    try:
        resp = await chat_or_raise("secretary.plan", messages, max_tokens=512, temperature=0.1)
    except Exception as exc:  # noqa: BLE001 — surface as empty plan, not crash
        log.warning("planner: chat_or_raise failed: %s", exc)
        return []
    return _parse_steps(resp.text)

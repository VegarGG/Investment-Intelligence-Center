"""Publish advice.persona.<slug>.v1."""

from __future__ import annotations

from data_bus import advice_persona, publish
from data_bus.publish import PublishTarget
from schema import AdviceV1


async def publish_advice(js: PublishTarget, advice: AdviceV1) -> str:
    if not advice.agent.startswith("persona."):
        raise ValueError(f"persona publisher expects persona.* agent; got {advice.agent}")
    slug = advice.agent.removeprefix("persona.")
    return await publish(js, advice_persona(slug), advice, idempotency_key=f"advice:{advice.id}")

"""Publish advice.fundamental.v1 to the bus."""

from __future__ import annotations

from data_bus import ADVICE_FUNDAMENTAL, publish
from data_bus.publish import PublishTarget
from schema import AdviceV1


async def publish_advice(js: PublishTarget, advice: AdviceV1) -> str:
    return await publish(js, ADVICE_FUNDAMENTAL, advice, idempotency_key=f"advice:{advice.id}")

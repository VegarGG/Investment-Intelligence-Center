"""Publish advice.quant.v1."""

from __future__ import annotations

from data_bus import ADVICE_QUANT, publish
from data_bus.publish import PublishTarget
from schema import AdviceV1


async def publish_advice(js: PublishTarget, advice: AdviceV1) -> str:
    return await publish(js, ADVICE_QUANT, advice, idempotency_key=f"advice:{advice.id}")

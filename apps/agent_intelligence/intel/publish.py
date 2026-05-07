"""Publish the three intel subjects to the bus (workflow 10 §5.11)."""

from __future__ import annotations

from data_bus import (
    INTEL_BRIEF,
    INTEL_DASHBOARD,
    INTEL_DIGEST,
    publish,
)
from data_bus.publish import PublishTarget
from schema import IntelBriefV1, IntelDashboardV1, IntelDigestV1


async def publish_all(
    js: PublishTarget,
    *,
    digest: IntelDigestV1,
    dashboard: IntelDashboardV1,
    brief: IntelBriefV1,
) -> None:
    await publish(js, INTEL_DIGEST, digest, idempotency_key=f"digest:{digest.id}")
    await publish(js, INTEL_DASHBOARD, dashboard)
    await publish(js, INTEL_BRIEF, brief)

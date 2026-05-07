"""Workflow 05 §2 — KV bucket guards.

KV operations require a live JetStream context, so the round-trip is
integration-only. The unit-level guard checks the canonical-bucket-name
gate.
"""

from __future__ import annotations

import pytest
from data_bus.kv import _assert_bucket
from data_bus.subjects import KV_BUCKETS


class TestBucketGate:
    @pytest.mark.parametrize("bucket", list(KV_BUCKETS))
    def test_canonical_bucket_passes(self, bucket: str) -> None:
        _assert_bucket(bucket)  # no raise

    def test_unknown_bucket_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown KV bucket"):
            _assert_bucket("does_not_exist")


@pytest.mark.integration
class TestKVRoundTrip:
    """Acceptance §10 — `nats kv ls` shows the three buckets after init."""

    @pytest.mark.asyncio
    async def test_put_get_round_trip(self) -> None:
        from data_bus.client import connect, jetstream
        from data_bus.kv import get, put
        from data_bus.streams import ensure_kv_buckets

        nc = await connect()
        try:
            js = await jetstream(nc)
            await ensure_kv_buckets(js)
            await put(js, "iic_state", "macro_regime", "rate_cut")
            assert await get(js, "iic_state", "macro_regime") == "rate_cut"
        finally:
            await nc.close()

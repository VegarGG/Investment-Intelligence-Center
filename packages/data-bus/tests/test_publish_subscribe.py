"""Workflow 05 §6 — publish() serialization, idempotency, header injection.

Unit tests use an in-memory PublishTarget stub. The wire-level NATS round-trip
lives in TestNatsRoundTrip behind the integration marker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import orjson
import pytest
from data_bus.exceptions import InvalidSubject
from data_bus.publish import publish
from pydantic import BaseModel


@dataclass
class _StubAck:
    seq: int = 1


@dataclass
class _RecordingTarget:
    """Mimics enough of JetStreamContext.publish for unit tests."""

    sent: list[dict[str, Any]] = field(default_factory=list)

    async def publish(
        self,
        subject: str,
        payload: bytes,
        *,
        headers: dict[str, str] | None = None,
    ) -> _StubAck:
        self.sent.append({"subject": subject, "payload": payload, "headers": headers or {}})
        return _StubAck(seq=len(self.sent))


class _Sample(BaseModel):
    schema_version: str = "demo.v1"
    value: int


class TestPublish:
    @pytest.mark.asyncio
    async def test_dict_payload_serialized_to_json_bytes(self) -> None:
        target = _RecordingTarget()
        msg_id = await publish(target, "intel.digest.v1", {"k": "v"})
        assert target.sent[0]["subject"] == "intel.digest.v1"
        decoded = orjson.loads(target.sent[0]["payload"])
        assert decoded == {"k": "v"}
        assert msg_id == "INTEL@1"

    @pytest.mark.asyncio
    async def test_pydantic_payload_serialized_via_model_dump(self) -> None:
        target = _RecordingTarget()
        await publish(target, "intel.digest.v1", _Sample(value=42))
        decoded = orjson.loads(target.sent[0]["payload"])
        assert decoded == {"schema_version": "demo.v1", "value": 42}

    @pytest.mark.asyncio
    async def test_idempotency_key_set_as_nats_msg_id(self) -> None:
        target = _RecordingTarget()
        msg_id = await publish(target, "intel.digest.v1", {"k": "v"}, idempotency_key="abc-123")
        assert target.sent[0]["headers"]["Nats-Msg-Id"] == "abc-123"
        assert msg_id == "abc-123"

    @pytest.mark.asyncio
    async def test_invalid_subject_rejected_before_any_send(self) -> None:
        target = _RecordingTarget()
        with pytest.raises(InvalidSubject):
            await publish(target, "advice.beta", {"k": "v"})
        assert target.sent == []

    @pytest.mark.asyncio
    async def test_unknown_stream_subject_rejected(self) -> None:
        # Subject is shape-valid (.v1) but doesn't match any stream prefix.
        target = _RecordingTarget()
        with pytest.raises(InvalidSubject, match="doesn't fall under any provisioned stream"):
            await publish(target, "custom.unbound.v1", {"k": "v"})

    @pytest.mark.asyncio
    async def test_content_type_header_set(self) -> None:
        target = _RecordingTarget()
        await publish(target, "intel.digest.v1", {"k": "v"})
        assert target.sent[0]["headers"]["Content-Type"] == "application/json"


@pytest.mark.integration
class TestNatsRoundTrip:
    """Acceptance §10 — publish → receive within 1s on a real NATS.

    Skipped without IIC_INTEGRATION=1; needs `docker compose up -d nats`."""

    @pytest.mark.asyncio
    async def test_advice_round_trip(self) -> None:
        import asyncio

        from data_bus.client import connect, jetstream
        from data_bus.streams import ensure_streams
        from data_bus.subscribe import subscribe

        nc = await connect()
        try:
            js = await jetstream(nc)
            await ensure_streams(js)

            received: list[bytes] = []
            done = asyncio.Event()

            async def handler(msg: Any) -> None:
                received.append(msg.data)
                done.set()

            sub = await subscribe(
                js,
                "advice.fundamental.v1",
                durable_name="test.round_trip",
                handler=handler,
            )

            await publish(js, "advice.fundamental.v1", {"k": "v"})
            await asyncio.wait_for(done.wait(), timeout=2.0)
            assert orjson.loads(received[0]) == {"k": "v"}
            await sub.cancel()
        finally:
            await nc.close()

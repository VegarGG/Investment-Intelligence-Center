"""Stream + KV-bucket provisioning helpers (workflow 05 §8.1).

These are idempotent admin calls — `infra/nats/init.sh` shells out to the
NATS CLI for the same operations during host bootstrap; this module is the
Python equivalent that the orchestrator can call at startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from data_bus.subjects import KV_BUCKETS, STREAMS, StreamSpec

if TYPE_CHECKING:
    from nats.js.client import JetStreamContext


async def ensure_streams(js: JetStreamContext) -> list[str]:
    """Create or update every stream in §2. Returns the list of names touched."""
    from nats.js.api import StreamConfig

    touched: list[str] = []
    for spec in STREAMS:
        cfg = _stream_config(spec)
        # nats-py StreamConfig has many optional fields with strict per-field
        # types; passing a kwargs dict is the cleanest authoring path even
        # though mypy can't narrow the **dict expansion to those types.
        stream_cfg: Any = StreamConfig(**cfg)
        try:
            await js.add_stream(stream_cfg)
        except Exception:  # already exists is the expected path; nats-py error type is unstable
            # Stream already exists — update in case retention changed.
            await js.update_stream(stream_cfg)
        touched.append(spec.name)
    return touched


async def ensure_kv_buckets(js: JetStreamContext) -> list[str]:
    """Create the three KV buckets per §2 if missing. Idempotent."""
    from contextlib import suppress

    from nats.js.api import KeyValueConfig

    touched: list[str] = []
    for bucket in KV_BUCKETS:
        # Already-exists is the expected path on re-run; nats-py raises a
        # provider-specific error we don't want to leak as a typed exception.
        with suppress(Exception):
            await js.create_key_value(KeyValueConfig(bucket=bucket))
        touched.append(bucket)
    return touched


def _stream_config(spec: StreamSpec) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "name": spec.name,
        "subjects": [spec.subject_prefix],
        "num_replicas": spec.replicas,
    }
    if spec.retention_seconds is not None:
        # max_age expects nanoseconds in the nats-py StreamConfig.
        cfg["max_age"] = spec.retention_seconds * 1_000_000_000
    return cfg

"""KV-bucket helpers for `iic_state`, `iic_locks`, `iic_versions` (workflow 05 §2)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from data_bus.subjects import KV_BUCKETS

if TYPE_CHECKING:
    from nats.js.client import JetStreamContext
    from nats.js.kv import KeyValue


def _assert_bucket(bucket: str) -> None:
    if bucket not in KV_BUCKETS:
        raise ValueError(f"unknown KV bucket {bucket!r}; canonical set is {KV_BUCKETS}")


async def kv(js: JetStreamContext, bucket: str) -> KeyValue:
    _assert_bucket(bucket)
    return await js.key_value(bucket)


async def get(js: JetStreamContext, bucket: str, key: str) -> str | None:
    """Read a key. Returns None if the key doesn't exist."""
    bucket_obj = await kv(js, bucket)
    try:
        entry = await bucket_obj.get(key)
    except Exception:
        return None
    return entry.value.decode() if entry.value else None


async def put(js: JetStreamContext, bucket: str, key: str, value: str) -> int:
    """Write a key, returns the resulting revision number."""
    bucket_obj = await kv(js, bucket)
    return int(await bucket_obj.put(key, value.encode()))


async def watch(
    js: JetStreamContext, bucket: str, key_pattern: str = ">"
) -> AsyncIterator[tuple[str, str | None]]:
    """Yield (key, value) pairs as they change. value is None for deletes."""
    bucket_obj = await kv(js, bucket)
    watcher: Any = await bucket_obj.watch(key_pattern)
    try:
        async for update in watcher.updates():
            if update is None:
                continue
            value = update.value.decode() if update.value else None
            yield update.key, value
    finally:
        await watcher.stop()

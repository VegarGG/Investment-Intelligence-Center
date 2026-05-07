"""Token-bucket rate limiter per (provider, tier) (workflow 03 §8).

Defaults:
  deepseek/flash    60 RPS
  deepseek/pro       6 RPS  + concurrency cap of 4 in-flight
  anthropic          5 RPS
  groq              20 RPS
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BucketConfig:
    rps: float
    concurrency: int | None = None  # None == unlimited


DEFAULTS: dict[tuple[str, str], BucketConfig] = {
    ("deepseek", "flash"): BucketConfig(rps=60.0),
    ("deepseek", "pro"): BucketConfig(rps=6.0, concurrency=4),
    ("deepseek", "embed"): BucketConfig(rps=20.0),
    ("anthropic", "pro"): BucketConfig(rps=5.0, concurrency=4),
    ("groq", "flash"): BucketConfig(rps=20.0),
}


class _Bucket:
    """Async token bucket. Refills at `rps` tokens/sec to a cap of 1 token."""

    __slots__ = ("rps", "_lock", "_next_ready", "_sem")

    def __init__(self, cfg: BucketConfig) -> None:
        self.rps = cfg.rps
        self._lock = asyncio.Lock()
        self._next_ready = 0.0
        self._sem = asyncio.Semaphore(cfg.concurrency) if cfg.concurrency else None

    async def acquire(self) -> None:
        if self._sem is not None:
            await self._sem.acquire()
        try:
            async with self._lock:
                now = time.monotonic()
                wait = max(0.0, self._next_ready - now)
                self._next_ready = max(now, self._next_ready) + 1.0 / self.rps
            if wait > 0:
                await asyncio.sleep(wait)
        except BaseException:
            if self._sem is not None:
                self._sem.release()
            raise

    def release(self) -> None:
        if self._sem is not None:
            self._sem.release()


class RateLimiter:
    """Per-(provider, tier) token bucket. acquire() blocks until allowed."""

    def __init__(self, overrides: dict[tuple[str, str], BucketConfig] | None = None) -> None:
        cfg = {**DEFAULTS, **(overrides or {})}
        self._buckets: dict[tuple[str, str], _Bucket] = {key: _Bucket(c) for key, c in cfg.items()}

    async def acquire(self, *, provider: str, tier: str) -> None:
        bucket = self._buckets.get((provider, tier))
        if bucket is None:
            return  # unconfigured combo — let the call through (e.g. unit tests)
        await bucket.acquire()

    def release(self, *, provider: str, tier: str) -> None:
        bucket = self._buckets.get((provider, tier))
        if bucket is not None:
            bucket.release()

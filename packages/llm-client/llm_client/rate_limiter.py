"""Token-bucket rate limiter per (provider, tier) (workflow 03 §8).

Defaults:
  deepseek/flash    60 RPS
  deepseek/pro       6 RPS  + concurrency cap of 4 in-flight
  deepseek/embed    20 RPS
  anthropic/pro      5 RPS  + concurrency cap of 4 in-flight
  groq/flash        20 RPS

P0.4 — env overrides. Set ``IIC_RATE_<PROVIDER>_<TIER>=<rps>`` to override
RPS, e.g. ``IIC_RATE_DEEPSEEK_PRO=8``. ``IIC_RATE_<PROVIDER>_<TIER>_CONC=N``
overrides the concurrency cap. Saves goodwill with the provider (we
throttle ourselves *before* the 429 storm) and lets ops dial back without
a redeploy.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BucketConfig:
    rps: float
    concurrency: int | None = None  # None == unlimited


_BUILTIN_DEFAULTS: dict[tuple[str, str], BucketConfig] = {
    ("deepseek", "flash"): BucketConfig(rps=60.0),
    ("deepseek", "pro"): BucketConfig(rps=6.0, concurrency=4),
    ("deepseek", "embed"): BucketConfig(rps=20.0),
    ("anthropic", "pro"): BucketConfig(rps=5.0, concurrency=4),
    ("groq", "flash"): BucketConfig(rps=20.0),
    # OpenAI is the embed fallback in the post-P2 matrix.
    ("openai", "embed"): BucketConfig(rps=20.0),
}


def _env_overrides() -> dict[tuple[str, str], BucketConfig]:
    """Resolve `IIC_RATE_<PROVIDER>_<TIER>=<rps>` env vars at load time.

    Compose effective config = builtin defaults overlaid with any env
    overrides present. Unparseable values are ignored (keep startup
    robust against a typo in ops config)."""
    out: dict[tuple[str, str], BucketConfig] = {}
    for raw_key, raw_val in os.environ.items():
        if not raw_key.startswith("IIC_RATE_"):
            continue
        body = raw_key[len("IIC_RATE_") :]
        is_conc = body.endswith("_CONC")
        if is_conc:
            body = body[: -len("_CONC")]
        parts = body.split("_")
        if len(parts) != 2:
            continue
        provider, tier = parts[0].lower(), parts[1].lower()
        key = (provider, tier)
        base = out.get(key, _BUILTIN_DEFAULTS.get(key, BucketConfig(rps=10.0)))
        try:
            if is_conc:
                conc = int(raw_val)
                out[key] = BucketConfig(rps=base.rps, concurrency=conc if conc > 0 else None)
            else:
                out[key] = BucketConfig(rps=float(raw_val), concurrency=base.concurrency)
        except ValueError:
            continue
    return out


def effective_defaults() -> dict[tuple[str, str], BucketConfig]:
    """Builtin defaults overlaid with `IIC_RATE_*` env overrides."""
    return {**_BUILTIN_DEFAULTS, **_env_overrides()}


# Backwards compat: existing callers reference `DEFAULTS` directly.
DEFAULTS: dict[tuple[str, str], BucketConfig] = effective_defaults()


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

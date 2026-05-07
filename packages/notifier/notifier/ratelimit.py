"""Per-channel rate limit (workflow 20 §11.2 + §13).

WeCom bot: 20/min/bot. Server酱: 5/min. ntfy: unlimited (LAN). SMTP: 50/hour.

Production stores the sliding window in Redis (`ratelimit:notifier:<adapter>`).
The unit tests use the in-memory backend below.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .adapters.base import AdapterRateLimit

DEFAULT_LIMITS: dict[str, tuple[int, float]] = {
    "wecom_bot:briefs": (20, 60.0),
    "wecom_bot:alerts": (20, 60.0),
    "wecom_bot:fills": (20, 60.0),
    "wecom_app": (60, 60.0),
    "serverchan": (5, 60.0),
    "ntfy": (1_000, 60.0),  # effectively unlimited
    "smtp": (50, 3600.0),
}

ClockFn = Callable[[], float]


@dataclass(slots=True)
class _Window:
    capacity: int
    window_s: float
    timestamps: deque[float]


class RateLimiter:
    """Sliding-window — for `acquire(key)` raises AdapterRateLimit if the
    `capacity` events in the last `window_s` seconds were already used."""

    def __init__(
        self,
        limits: dict[str, tuple[int, float]] | None = None,
        *,
        clock: ClockFn = time.monotonic,
    ) -> None:
        self._limits = limits or DEFAULT_LIMITS
        self._clock = clock
        self._windows: dict[str, _Window] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str) -> None:
        async with self._lock:
            cap, window_s = self._limits.get(key, (0, 0.0))
            if cap == 0:
                return  # uncapped
            window = self._windows.setdefault(key, _Window(cap, window_s, deque()))
            now = self._clock()
            cutoff = now - window.window_s
            while window.timestamps and window.timestamps[0] < cutoff:
                window.timestamps.popleft()
            if len(window.timestamps) >= window.capacity:
                raise AdapterRateLimit(f"{key}: {window.capacity}/{window.window_s}s exhausted")
            window.timestamps.append(now)

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._windows.clear()
        else:
            self._windows.pop(key, None)


async def with_retry_after(
    fn: Callable[[], Awaitable[None]],
    *,
    sleep_s: float = 1.0,
    max_attempts: int = 3,
) -> None:
    """Tiny back-off helper — sleep then retry on `AdapterRateLimit`."""
    for attempt in range(max_attempts):
        try:
            await fn()
            return
        except AdapterRateLimit:
            if attempt + 1 == max_attempts:
                raise
            await asyncio.sleep(sleep_s * (2**attempt))

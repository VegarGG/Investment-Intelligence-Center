"""YAML-backed feature flag core (v2.5 T0.1).

Design notes
------------
- Mtime-cached reload, not inotify, because the Mac mini dev host and the
  Linux prod host both share this file via bind mount. Mtime poll on read
  costs ~1µs and is good enough for 2 s flip latency at the call sites
  this package is used at.
- Test overrides live in a contextvar-free dict because the existing
  StateGraph runner relies on per-DAG-node coroutines; we keep the API
  simple and explicit (`set_for_test` / `reset_for_test`).
- A flag must be `register()`'d before `flag()` will return True for it,
  preventing typo-driven silent-False at call sites.
"""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml

T = TypeVar("T")

DEFAULT_PATH = "/srv/iic/featureflags/flags.yaml"


@dataclass(frozen=True, slots=True)
class FlagSpec:
    name: str
    description: str
    added_in: str
    default: Any
    owner: str


@dataclass(slots=True)
class _Cache:
    mtime: float = -1.0
    values: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, FlagSpec] = {}
_TEST_OVERRIDES: dict[str, Any] = {}
_CACHE = _Cache()
_LOCK = threading.Lock()


def _flags_path() -> Path:
    return Path(os.environ.get("IIC_FEATUREFLAGS_PATH", DEFAULT_PATH))


def _read_yaml() -> dict[str, Any]:
    p = _flags_path()
    if not p.exists():
        return {}
    with _LOCK:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            return dict(_CACHE.values)
        if mtime != _CACHE.mtime:
            try:
                raw = yaml.safe_load(p.read_text()) or {}
            except yaml.YAMLError:
                return dict(_CACHE.values)
            if not isinstance(raw, dict):
                raw = {}
            _CACHE.mtime = mtime
            _CACHE.values = {str(k): v for k, v in raw.items()}
        return dict(_CACHE.values)


def register(
    name: str,
    *,
    description: str,
    added_in: str,
    default: Any = False,
    owner: str = "iic",
) -> FlagSpec:
    """Declare a flag. Idempotent; later calls overwrite the registry entry.

    Every new agent / DAG / endpoint should register its flags at import time
    so `docs/featureflags.md` stays canonical.
    """

    spec = FlagSpec(
        name=name,
        description=description,
        added_in=added_in,
        default=default,
        owner=owner,
    )
    _REGISTRY[name] = spec
    return spec


def _resolve(name: str) -> Any:
    if name in _TEST_OVERRIDES:
        return _TEST_OVERRIDES[name]
    values = _read_yaml()
    if name in values:
        return values[name]
    spec = _REGISTRY.get(name)
    if spec is None:
        return None
    return spec.default


def flag(name: str) -> bool:
    """Return True iff `name` is registered AND resolves truthy.

    Unregistered names always return False so a typo can't accidentally
    enable a code path."""
    if name not in _REGISTRY:
        return False
    return bool(_resolve(name))


def flag_value(name: str, default: T) -> T:
    """Return the current scalar value for `name`, or `default` if absent.

    Unlike `flag()`, this allows numeric / string flags (e.g. throttle
    limits) to be tuned via the YAML without code change.
    """
    raw = _resolve(name)
    if raw is None:
        return default
    return cast(T, raw)


@contextlib.asynccontextmanager
async def with_flag(name: str) -> AsyncIterator[bool]:
    """Async context manager that yields the current flag value.

    Used at call sites that want to take a different code path while
    remaining easy to grep and easy to deprecate later.
    """
    yield flag(name)


def set_for_test(name: str, value: Any) -> None:
    _TEST_OVERRIDES[name] = value


def reset_for_test() -> None:
    _TEST_OVERRIDES.clear()


def list_flags() -> list[dict[str, Any]]:
    """Snapshot of every registered flag + its current resolved value.

    Powers the `/featureflags` admin endpoint and the Grafana panel.
    """
    return [
        {
            "name": s.name,
            "description": s.description,
            "added_in": s.added_in,
            "default": s.default,
            "owner": s.owner,
            "current": _resolve(s.name),
        }
        for s in sorted(_REGISTRY.values(), key=lambda x: x.name)
    ]

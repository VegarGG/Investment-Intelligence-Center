"""Repo-root resolution (P1.6).

Single canonical answer to "where does the IIC checkout live?" for
container *and* developer-workstation runs. Replaces the per-call-site
``Path(__file__).resolve().parents[N]`` arithmetic that broke whenever
the filesystem layout changed (D6 §1.1 patch #7).

Resolution order:
  1. ``IIC_REPO_ROOT`` env var, if set.
  2. The git-tracked checkout the caller's module lives under, walking
     up looking for ``pyproject.toml`` + a ``packages/`` directory (the
     two markers that uniquely identify the IIC monorepo).
  3. ``/app`` as a final fallback for containerised installs.

All shared assets (``docs/prompts/persona``, ``infra/intel/*``, fixtures)
should be addressed as ``repo_root() / "docs" / "prompts" / "persona"``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the IIC repository root."""
    env = os.environ.get("IIC_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "packages").is_dir():
            return parent
    return Path("/app")


def persona_dir() -> Path:
    """``$IIC_PERSONA_DIR`` override, else ``<repo_root>/docs/prompts/persona``."""
    env = os.environ.get("IIC_PERSONA_DIR")
    if env:
        return Path(env).resolve()
    return repo_root() / "docs" / "prompts" / "persona"


def reset_for_test() -> None:
    """Drop the cached ``repo_root()`` result. Tests that monkeypatch
    ``IIC_REPO_ROOT`` must call this before re-reading."""
    repo_root.cache_clear()

"""P1.6 — repo_root() resolution must be robust to env override and layout."""

from __future__ import annotations

from pathlib import Path

import pytest

from featureflags import paths


@pytest.fixture(autouse=True)
def _reset_cache():
    paths.reset_for_test()
    yield
    paths.reset_for_test()


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("IIC_REPO_ROOT", str(tmp_path))
    assert paths.repo_root() == tmp_path.resolve()


def test_persona_dir_under_repo_root(monkeypatch, tmp_path):
    monkeypatch.setenv("IIC_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("IIC_PERSONA_DIR", raising=False)
    assert paths.persona_dir() == (tmp_path / "docs" / "prompts" / "persona").resolve() or \
        paths.persona_dir() == tmp_path / "docs" / "prompts" / "persona"


def test_persona_dir_env_overrides_default(monkeypatch, tmp_path):
    monkeypatch.setenv("IIC_PERSONA_DIR", str(tmp_path / "custom_personas"))
    assert paths.persona_dir() == (tmp_path / "custom_personas").resolve()


def test_repo_root_walks_to_marker_when_unset(monkeypatch):
    """Without IIC_REPO_ROOT, walk up looking for pyproject.toml + packages/."""
    monkeypatch.delenv("IIC_REPO_ROOT", raising=False)
    root = paths.repo_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "packages").is_dir()


def test_repo_root_falls_back_to_app(monkeypatch, tmp_path):
    """When IIC_REPO_ROOT points to a path that doesn't exist, accept the
    env var rather than walking past — environments may not have the
    on-disk markers (e.g. a stripped container)."""
    monkeypatch.setenv("IIC_REPO_ROOT", str(tmp_path / "deleted"))
    # The cache hasn't been cleared; explicitly reset.
    paths.reset_for_test()
    assert paths.repo_root() == Path(tmp_path / "deleted").resolve()

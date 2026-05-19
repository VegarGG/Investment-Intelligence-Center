"""P3.1 — config_io read/propose/apply with whitelist enforcement."""

from __future__ import annotations

import featureflags.paths as paths
import pytest

from admin_api import config_io


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """Drop a synthetic repo layout into tmp_path and point repo_root() at it."""
    (tmp_path / "packages").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.iic]\n")
    (tmp_path / "infra" / "intel").mkdir(parents=True)
    (tmp_path / "docs" / "prompts" / "persona").mkdir(parents=True)
    monkeypatch.setenv("IIC_REPO_ROOT", str(tmp_path))
    paths.reset_for_test()
    return tmp_path


def test_editable_paths_whitelist(fake_repo):
    paths_list = list(config_io.editable_paths())
    assert any("docs/prompts/persona/" in p for p, _ in paths_list)
    assert any("infra/cron/schedules.yaml" in p for p, _ in paths_list)


def test_read_missing_file_returns_empty(fake_repo):
    snap = config_io.read("infra/intel/macro-series.yaml")
    assert snap.content == ""
    assert snap.sha256


def test_apply_writes_yaml_atomically(fake_repo):
    rel = "infra/intel/macro-series.yaml"
    yaml_str = "fred:\n  - GS10\n  - CPIAUCSL\n"
    snap = config_io.apply(rel, yaml_str)
    on_disk = (fake_repo / rel).read_text()
    assert on_disk == yaml_str
    assert snap.sha256 == config_io.read(rel).sha256


def test_propose_detects_bad_yaml(fake_repo):
    with pytest.raises(ValueError):
        config_io.propose("infra/intel/macro-series.yaml", "key: [unterminated")


def test_propose_reports_before_and_after_hash(fake_repo):
    rel = "infra/intel/macro-series.yaml"
    config_io.apply(rel, "fred:\n  - GS10\n")
    proposed = config_io.propose(rel, "fred:\n  - GS10\n  - GS2\n")
    assert proposed["before_sha256"] != proposed["after_sha256"]


def test_path_outside_whitelist_rejected(fake_repo):
    with pytest.raises(PermissionError):
        config_io.read("../../../etc/passwd")
    with pytest.raises(PermissionError):
        config_io.apply("README.md", "x")

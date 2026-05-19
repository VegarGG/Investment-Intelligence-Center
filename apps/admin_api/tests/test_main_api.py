"""P3.1 — happy path end-to-end against the FastAPI TestClient."""

from __future__ import annotations

import featureflags.paths as paths
import pytest
from fastapi.testclient import TestClient

from admin_api import audit
from admin_api.main import app, set_audit_sink


@pytest.fixture(autouse=True)
def _fake_repo(tmp_path, monkeypatch):
    (tmp_path / "packages").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.iic]\n")
    (tmp_path / "infra" / "intel").mkdir(parents=True)
    (tmp_path / "infra" / "cron").mkdir(parents=True)
    monkeypatch.setenv("IIC_REPO_ROOT", str(tmp_path))
    paths.reset_for_test()
    set_audit_sink(audit.InMemoryAuditSink())
    yield tmp_path
    set_audit_sink(audit.InMemoryAuditSink())


def test_health_ok():
    client = TestClient(app)
    r = client.get("/admin/health")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "admin_api"
    assert "infra/cron/schedules.yaml" in body["editable_paths"]


def test_propose_then_apply_round_trip(_fake_repo):
    client = TestClient(app)
    rel = "infra/intel/macro-series.yaml"
    body = "fred:\n  - GS10\n"
    r1 = client.post(f"/admin/files/{rel}/propose", json={"content": body})
    assert r1.status_code == 200, r1.text
    assert r1.json()["after_sha256"]
    r2 = client.post(f"/admin/files/{rel}/apply", json={"content": body, "reason": "test"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["audit_id"]
    on_disk = (_fake_repo / rel).read_text()
    assert on_disk == body


def test_audit_head_advances_after_apply(_fake_repo):
    client = TestClient(app)
    assert client.get("/admin/audit/head").json()["head"] is None
    client.post(
        "/admin/files/infra/intel/macro-series.yaml/apply",
        json={"content": "fred:\n  - GS10\n"},
    )
    assert client.get("/admin/audit/head").json()["head"] is not None


def test_invalid_yaml_rejected(_fake_repo):
    client = TestClient(app)
    r = client.post(
        "/admin/files/infra/intel/macro-series.yaml/apply",
        json={"content": "key: [unterminated"},
    )
    assert r.status_code == 400


def test_path_outside_whitelist_rejected():
    client = TestClient(app)
    r = client.get("/admin/files/README.md")
    assert r.status_code == 403

"""v2.5 T1.3 acceptance — pipeline is bound at startup, /health/deep returns 200.

Workflow 10 §6 + plan v2.5 §T1.3.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from intel.factory import IntelConfig, build_pipeline
from intel.main import app, set_pipeline
from intel.types import RawEvent, SourceCfg


def _src(sid: str = "rss:us") -> SourceCfg:
    return SourceCfg(id=sid, region="US", lean="center", region_weight=1.0, language="en")


def _raw(source: str, title: str) -> RawEvent:
    when = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    return RawEvent(
        source_id=source,
        event_ts=when,
        ingest_ts=when,
        url=f"https://e/{title.replace(' ', '_')}",
        title=title,
        body=title,
        lang="en",
    )


def test_build_pipeline_with_no_config():
    """Bare `build_pipeline()` returns a runnable IntelPipeline."""
    pipeline = build_pipeline()
    assert pipeline is not None
    assert pipeline.sources == []


@pytest.mark.asyncio
async def test_build_pipeline_runs_one_doc():
    """A 1-doc dry-run completes inside the SLA (T1.3 acceptance)."""
    config = IntelConfig(sources=[_src()])
    pipeline = build_pipeline(
        config,
        test_events=[("rss:us", [_raw("rss:us", "Fed signals slower hikes")])],
    )
    result = await pipeline.run()
    assert len(result.accepted_events) == 1
    assert result.digest is not None


def test_health_deep_503_when_unbound():
    """`/health/deep` must surface unbound state explicitly."""
    set_pipeline(None)
    client = TestClient(app)
    r = client.get("/health/deep")
    assert r.status_code == 503
    assert "not bound" in r.json()["detail"]


@pytest.mark.asyncio
async def test_health_deep_200_when_bound():
    """`/health/deep` returns 200 once a pipeline is set."""
    config = IntelConfig(sources=[_src()])
    pipeline = build_pipeline(
        config,
        test_events=[("rss:us", [_raw("rss:us", "Fed signals slower hikes")])],
    )
    set_pipeline(pipeline)
    try:
        client = TestClient(app)
        r = client.get("/health/deep")
        assert r.status_code == 200
        body = r.json()
        assert body["events_accepted"] == 1
    finally:
        set_pipeline(None)


def test_health_root_reports_pipeline_bound():
    set_pipeline(None)
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["pipeline_bound"] is False

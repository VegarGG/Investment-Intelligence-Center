"""P9.6 — hermetic surrogate for the first-live-trace test.

Walks the full pipeline using StubAgentClient + the existing trading-room
DAG so we have an in-CI gate that fails the moment the topology breaks.
The corresponding *live* trace is the real definition of done; this
stub catches every wiring regression along the way.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.app import register_default_dags
from orchestrator.plan.agent_client import StubAgentClient
from orchestrator.plan.registry import REGISTRY, clear, lookup


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(REGISTRY)
    clear()
    yield
    clear()
    REGISTRY.update(saved)


def test_topology_supports_event_driven_path():
    """The orchestrator's registry must register the high-impact +
    geo_cluster event subjects with a runnable callable. This is the
    chain that the first live trace will travel."""
    register_default_dags(StubAgentClient(responses={}))
    assert lookup("event:intel.event.high_impact.v1") is not None
    assert lookup("event:intel.event.geo_cluster.v1") is not None


def test_topology_supports_user_driven_path():
    """Secretary's /chat dispatches outbound through HttpxAgentClient;
    here we assert all the cron-driven DAGs that secretary calls into
    are registered."""
    register_default_dags(StubAgentClient(responses={}))
    for name in (
        "cron:morning_brief",
        "cron:midday_check",
        "cron:evening_recap",
        "cron:intel_rss_pull",
        "cron:intel_gdelt_pull",
        "cron:intel_macro_pull",
    ):
        assert lookup(name) is not None, f"{name} missing from registry"


@pytest.mark.asyncio
async def test_event_triggers_trading_room_dag_via_stub():
    """Fire a synthetic high-impact event and verify the registered DAG
    can be invoked without raising. (The full execution path requires
    NATS + the agents themselves; we only verify the orchestrator side
    here.)"""
    client = StubAgentClient(
        responses={
            ("agent_quant", "team_plan"): {"plan": {"team": "quant"}},
            ("agent_fundamental", "team_plan"): {"plan": {"team": "fundamental"}},
            ("agent_persona", "team_plan"): {"plan": {"team": "persona"}},
            ("agent_board", "decide"): {"decision": "go"},
            ("agent_secretary", "compose_brief"): {"markdown": "ok"},
            ("agent_secretary", "notify"): {"ok": True},
        }
    )
    register_default_dags(client)
    runner = lookup("event:intel.event.high_impact.v1")
    assert runner is not None
    payload: dict[str, Any] = {
        "trace_id": "t-1",
        "payload": {
            "event_id": "evt-1",
            "trace_id": "t-1",
            "tickers": ["AAPL"],
            "title": "Apple Q3",
            "body": "earnings beat",
            "regime_change_score": 0.6,
            "surprise_factor": 0.7,
            "affected_universe_overlap": 0.8,
        },
    }
    # The orchestrator's run dispatcher returns DagResult on success.
    result = await runner(payload)
    assert result is not None

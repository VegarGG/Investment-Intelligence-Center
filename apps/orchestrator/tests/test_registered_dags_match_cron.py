"""v2.5 T1.5e — fail closed if a cron entry has no registered DAG.

Plan v2.5 §T1.5: every cron job must map to a registered DAG; every NATS
subscription must map to a registered DAG. v2.1 dropped 4-of-5 crons and
3-of-3 subscriptions silently. This test makes that impossible to
re-introduce.
"""

from __future__ import annotations

import pytest
from orchestrator.app import register_default_dags
from orchestrator.plan.agent_client import StubAgentClient
from orchestrator.plan.registry import REGISTRY, clear, lookup
from orchestrator.triggers.cron import CRON_JOBS
from orchestrator.triggers.nats_events import ORCH_SUBSCRIPTIONS


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(REGISTRY)
    clear()
    yield
    clear()
    REGISTRY.update(saved)


def test_every_cron_has_a_registered_dag():
    register_default_dags(StubAgentClient(responses={}))
    missing = []
    for cron_name, _kwargs in CRON_JOBS:
        if lookup(cron_name) is None:
            missing.append(cron_name)
    assert not missing, (
        f"v2.5 T1.5: cron entries with no registered DAG: {missing}. "
        "Every cron must map 1:1 onto a DAG (plan §T1.5e)."
    )


def test_every_nats_subscription_has_a_registered_dag():
    register_default_dags(StubAgentClient(responses={}))
    missing = []
    for subject, _durable in ORCH_SUBSCRIPTIONS:
        trigger_name = f"event:{subject}"
        if lookup(trigger_name) is None:
            missing.append(trigger_name)
    assert not missing, (
        f"v2.5 T1.5: NATS subjects with no registered DAG: {missing}. "
        "Every subscription must map 1:1 onto a DAG."
    )


def test_morning_brief_still_registered():
    """Sanity — refactor must not have regressed v2.1's only registered DAG."""
    register_default_dags(StubAgentClient(responses={}))
    assert lookup("cron:morning_brief") is not None
    assert lookup("http:morning_brief") is not None

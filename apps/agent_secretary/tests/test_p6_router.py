"""P6 — secretary as leader-router. Chat dispatch + prefs + rerun + memory."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from secretary import main as main_mod
from secretary.agents import StubAgentClient
from secretary.memory import InMemoryThreadStore
from secretary.prefs import InMemoryPrefStore


@pytest.fixture
def stub_app(monkeypatch):
    monkeypatch.setenv("SECRETARY_ALLOWED_USERS", "u1,u2")
    stub = StubAgentClient(
        responses={
            ("agent_intelligence", "/run/context"): {"ticker": "AAPL", "events": 12},
            ("agent_persona", "/run/rerun"): {"ok": True, "slug": "buffett"},
            ("agent_intelligence", "/run/synthesize"): {"status": "ok", "events": 5},
            ("orchestrator", "/run/morning_brief"): {"status": "ok"},
            ("agent_backtest", "/run/daily_mtm"): {"status": "ok", "agents": []},
        }
    )
    main_mod.set_agents(stub)
    main_mod.set_prefs(InMemoryPrefStore())
    main_mod.set_thread_store(InMemoryThreadStore())

    async def fake_plan(text, *, context_turns=None):
        from secretary.planner import PlanStep

        if "AAPL" in text:
            return [PlanStep(caller="agent_intelligence", endpoint="/run/context", args={"ticker": "AAPL"})]
        if "Buffett" in text or "rerun" in text:
            return [PlanStep(caller="agent_persona", endpoint="/run/rerun", args={"slug": "buffett"})]
        return []

    monkeypatch.setattr(main_mod, "planner_plan", fake_plan)
    return TestClient(main_mod.app), stub


def test_chat_dispatches_planner_step(stub_app):
    client, stub = stub_app
    r = client.post("/chat", json={"text": "tell me about AAPL", "user_id": "u1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["steps"]) == 1
    assert body["steps"][0]["caller"] == "agent_intelligence"
    assert body["results"][0]["result"]["events"] == 12
    # The stub agent recorded the call.
    assert stub.calls == [
        ("agent_intelligence", "/run/context", {"ticker": "AAPL"})
    ]


def test_chat_persists_to_memory(stub_app):
    client, _ = stub_app
    r1 = client.post("/chat", json={"text": "tell me about AAPL", "user_id": "u1"})
    tid = r1.json()["thread_id"]
    r2 = client.post("/chat", json={"text": "tell me about AAPL", "user_id": "u1", "thread_id": tid})
    assert r2.json()["thread_id"] == tid
    # Memory store should now hold 2 user + 2 assistant turns.
    assert len(main_mod.threads.turns) == 4


def test_rerun_dispatches(stub_app):
    client, stub = stub_app
    r = client.post(
        "/rerun",
        json={"agent": "agent_persona", "override_signals": {"slug": "buffett", "focus": "AAPL"}},
    )
    assert r.status_code == 200
    assert r.json()["result"]["slug"] == "buffett"
    assert stub.calls[-1] == (
        "agent_persona",
        "/run/rerun",
        {"slug": "buffett", "focus": "AAPL"},
    )


def test_prefs_round_trip(stub_app):
    client, _ = stub_app
    r1 = client.put("/prefs/u1/tone", json={"value": "terse"})
    assert r1.status_code == 200
    r2 = client.get("/prefs/u1")
    assert r2.json()["prefs"]["tone"] == "terse"


def test_quiet_slash_mutates_prefs(stub_app):
    client, _ = stub_app
    r = client.post(
        "/notifier/wecom/callback",
        headers={"X-WeCom-UserId": "u1"},
        content="/quiet 45",
    )
    assert r.status_code == 200
    r2 = client.get("/prefs/u1")
    assert "mute_until" in r2.json()["prefs"]


def test_morning_brief_real_composition(stub_app):
    client, stub = stub_app
    r = client.post("/run/morning_brief")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "morning_brief"
    assert "Morning brief" in body["markdown"]
    # Verify the secretary actually fanned out — no more "queued" placeholder.
    callers = [c[0] for c in stub.calls]
    assert "agent_intelligence" in callers
    assert "orchestrator" in callers

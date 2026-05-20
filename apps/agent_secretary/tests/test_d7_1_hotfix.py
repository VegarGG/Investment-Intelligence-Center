"""D7.1 hotfix tests — H1.1 (chat user passthrough) + H1.2 (/chat/echo)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from secretary import main as main_mod
from secretary.agents import StubAgentClient
from secretary.memory import InMemoryThreadStore
from secretary.prefs import InMemoryPrefStore


@pytest.fixture
def stub_app(monkeypatch):
    """Mirror of the test_p6_router fixture: stub agents + planner + stores."""
    monkeypatch.setenv("SECRETARY_ALLOWED_USERS", "ziwei,u1")
    stub = StubAgentClient(
        responses={("agent_intelligence", "/run/context"): {"events": 1}}
    )
    main_mod.set_agents(stub)
    main_mod.set_prefs(InMemoryPrefStore())
    main_mod.set_thread_store(InMemoryThreadStore())

    async def fake_plan(text, *, context_turns=None):
        return []

    monkeypatch.setattr(main_mod, "planner_plan", fake_plan)
    return TestClient(main_mod.app)


# ----- H1.1 — chat user passthrough ------------------------------------------


def test_chat_accepts_user_field_in_body(stub_app):
    """Bringup-style call: ``{"user":"ziwei","text":"hi"}`` must resolve
    to user_id="ziwei", not the "anon" fallback."""
    r = stub_app.post("/chat", json={"user": "ziwei", "text": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "ziwei"


def test_chat_accepts_user_id_field_in_body(stub_app):
    """Backwards-compat: P6's original ``user_id`` field still works."""
    r = stub_app.post("/chat", json={"user_id": "u1", "text": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "u1"


def test_chat_prefers_header_over_body(stub_app):
    """X-User-Id header must override body so body content cannot
    impersonate an authenticated caller."""
    r = stub_app.post(
        "/chat",
        json={"user": "u1", "text": "hi"},
        headers={"X-User-Id": "ziwei"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "ziwei"


def test_chat_allowlist_case_insensitive(stub_app):
    """Allow-list comparison is lowercased; ZIWEI matches ziwei."""
    r = stub_app.post("/chat", json={"user": "ZIWEI", "text": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "ziwei"


def test_chat_anon_blocked_when_allowlist_set(stub_app):
    """No user provided + allowlist set → 403, not silent dispatch."""
    r = stub_app.post("/chat", json={"text": "hi"})
    assert r.status_code == 403
    assert r.json()["detail"]["user_id"] == "anon"


def test_chat_permissive_when_allowlist_unset(monkeypatch):
    """An empty allow-list is treated as "no allow-list" — fresh dev
    installs work without configuring users (D7.1 §H1.1 acceptance)."""
    monkeypatch.delenv("SECRETARY_ALLOWED_USERS", raising=False)
    stub = StubAgentClient(responses={})
    main_mod.set_agents(stub)
    main_mod.set_prefs(InMemoryPrefStore())
    main_mod.set_thread_store(InMemoryThreadStore())

    async def fake_plan(text, *, context_turns=None):
        return []

    monkeypatch.setattr(main_mod, "planner_plan", fake_plan)
    client = TestClient(main_mod.app)
    r = client.post("/chat", json={"text": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "anon"


# ----- H1.2 — /chat/echo demo endpoint ---------------------------------------


def test_chat_echo_returns_llm_call_id(stub_app):
    """The whole point of /chat/echo: produce an llm_call_id the smoke
    gate can correlate with a row in lake.llm_calls."""
    r = stub_app.post("/chat/echo", json={"text": "hello world"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm_call_id"]  # non-empty
    assert body["model"]
    assert "latency_ms" in body
    assert "echo" in body


def test_chat_echo_bypasses_allowlist(stub_app):
    """Even with SECRETARY_ALLOWED_USERS set, /chat/echo lets through
    unauthenticated callers — the smoke gate has no allowlist to fight."""
    r = stub_app.post("/chat/echo", json={"text": "hi"})
    assert r.status_code == 200


def test_chat_echo_404_when_demo_disabled(stub_app, monkeypatch):
    monkeypatch.setenv("SECRETARY_DEMO_ENDPOINTS", "off")
    r = stub_app.post("/chat/echo", json={"text": "hi"})
    assert r.status_code == 404


def test_chat_echo_400_on_missing_text(stub_app):
    r = stub_app.post("/chat/echo", json={"text": ""})
    assert r.status_code == 400

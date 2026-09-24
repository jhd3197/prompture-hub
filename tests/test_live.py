"""Live event bus and GET /v1/live."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time

import pytest
from fastapi.testclient import TestClient

ADMIN = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("HUB_DB_PATH", tmp.name)
    monkeypatch.setenv("HUB_ADMIN_TOKEN", "test-token")
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    from prompture_hub.storage import db as db_module

    db_module._engine = None
    db_module.init_db()
    from prompture_hub.live import get_bus

    get_bus().reset()
    yield
    get_bus().reset()
    get_settings.cache_clear()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


def _key(**extra) -> str:
    r = _client().post("/admin/keys", headers=ADMIN, json={"name": "app", "daily_spend_cap_usd": 100.0, **extra})
    return r.json()["key"]


class _Driver:
    supports_messages = True
    supports_streaming = True

    def generate_messages(self, messages, options):
        return {"text": "secret answer", "meta": {"prompt_tokens": 2, "completion_tokens": 3, "cost": 0.25}}

    def generate_messages_stream(self, messages, options):
        yield {"type": "delta", "text": "secret "}
        yield {"type": "delta", "text": "answer"}
        yield {"type": "done", "text": "secret answer", "meta": {"prompt_tokens": 2, "completion_tokens": 3, "cost": 0.25}}


@pytest.fixture
def stub_driver(monkeypatch):
    import prompture.drivers as drivers_mod

    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda _m: _Driver())


def _events(url: str, headers: dict | None = None) -> list[dict]:
    out = []
    with _client().stream("GET", url, headers=headers or ADMIN) as r:
        assert r.status_code == 200, r.read()
        for line in r.iter_lines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


class TestBus:
    def test_publish_replay_and_running(self):
        from prompture_hub.live import get_bus

        bus = get_bus()
        bus.publish("request.started", {"request_id": "r1", "key_id": 1})
        bus.publish("request.first_token", {"request_id": "r1", "key_id": 1, "ttft_ms": 40})
        assert [e["request_id"] for e in bus.running()] == ["r1"]
        assert bus.running()[0]["ttft_ms"] == 40
        bus.publish("request.finished", {"request_id": "r1", "key_id": 1})
        assert bus.running() == []
        assert [e["type"] for e in bus.replay(1)] == ["request.first_token", "request.finished"]
        assert bus.last_id() == 3

    def test_abandoned_calls_expire(self, monkeypatch):
        from prompture_hub import live

        bus = live.get_bus()
        bus.publish("request.started", {"request_id": "old", "key_id": 1})
        monkeypatch.setattr(live, "IN_FLIGHT_TTL", -1)
        assert bus.running() == []

    def test_visibility(self):
        from prompture_hub.live import visible

        assert visible({"key_id": 3}, None)
        assert visible({"key_id": 3}, [3, 4])
        assert not visible({"key_id": 5}, [3, 4])
        assert visible({"type": "alert"}, [3])


class TestEndpoint:
    def test_requires_companion_credential(self):
        key = _key()
        r = _client().get("/v1/live?limit=1", headers={"Authorization": f"Bearer {key}"})
        assert r.status_code == 401

    def test_snapshot_lists_running_calls(self):
        from prompture_hub import metering
        from prompture_hub.storage.models import HubKey

        call = metering.begin(HubKey(id=7, name="bot", hashed_secret="x"), "openai/gpt-4o", "/v1/chat/completions", "web")
        [snapshot] = _events("/v1/live?limit=1")
        assert snapshot["type"] == "snapshot"
        [running] = snapshot["running"]
        assert running["request_id"] == call.request_id
        assert (running["key_name"], running["project"]) == ("bot", "web")

    def test_replay_after_a_call_carries_metadata_only(self, stub_driver):
        key = _key(default_project="docs")
        r = _client().post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "secret question"}]},
        )
        assert r.status_code == 200
        events = _events("/v1/live?after=0&limit=2")
        assert [e["type"] for e in events] == ["request.started", "request.finished"]
        started, finished = events
        assert started["request_id"] == finished["request_id"]
        assert finished["project"] == "docs"
        assert finished["cost_usd"] == pytest.approx(0.25)
        assert finished["status"] == "ok"
        raw = json.dumps(events)
        assert "secret" not in raw

    def test_last_event_id_header_resumes(self, stub_driver):
        from prompture_hub.live import get_bus

        get_bus().publish("request.started", {"request_id": "a", "key_id": None})
        get_bus().publish("request.finished", {"request_id": "a", "key_id": None})
        events = _events("/v1/live?limit=1", headers={**ADMIN, "Last-Event-ID": "1"})
        assert [e["id"] for e in events] == [2]

    def test_streamed_call_reports_first_token(self, stub_driver):
        key = _key()
        with _client().stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "openai/gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": "x"}]},
        ) as r:
            list(r.iter_lines())
        events = _events("/v1/live?after=0&limit=3")
        assert [e["type"] for e in events] == ["request.started", "request.first_token", "request.finished"]
        assert events[0]["stream"] is True
        assert events[2]["ttft_ms"] is not None

    def test_live_delivery(self):
        from prompture_hub.live import get_bus

        def later():
            time.sleep(0.3)
            get_bus().publish("request.started", {"request_id": "late", "key_id": None})

        threading.Thread(target=later, daemon=True).start()
        events = _events("/v1/live?limit=2")
        assert [e["type"] for e in events] == ["snapshot", "request.started"]
        assert events[1]["request_id"] == "late"

    def test_info_advertises_live(self):
        assert _client().get("/v1/companion/info").json()["features"]["live"] == "/v1/live"


def test_agent_lines_become_activity():
    from prompture_hub import metering
    from prompture_hub.live import get_bus
    from prompture_hub.routers.coding_agents import _track_agent_line
    from prompture_hub.storage.models import HubKey

    call = metering.begin(HubKey(id=1, name="k", hashed_secret="x"), "claude-code", "/v1/coding-agents/run")
    for payload in ({"type": "tool_call"}, {"type": "tool_result"}, {"type": "question"}, {"type": "message"}):
        _track_agent_line(call, f"data: {json.dumps(payload)}\n\n")
    _track_agent_line(call, "data: [DONE]\n\n")
    states = [(e["state"], e["event"]) for e in get_bus().replay(0) if e["type"] == "request.activity"]
    assert states == [("working", "tool_call"), ("waiting", "question"), ("working", "message")]
    assert get_bus().running()[0]["state"] == "working"

"""Anthropic-compatible /v1/messages: auth headers, model mapping, tools, streaming, metering."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from prompture.agents.live_events import MessageStop, TextDelta, ToolUseStart, ToolUseStop
from sqlmodel import select


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
    yield
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client():
    from fastapi.testclient import TestClient

    from prompture_hub.main import app
    return TestClient(app)


def _key(**extra) -> str:
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": "Bearer test-token"},
        json={"name": "claude-code", "daily_spend_cap_usd": 100.0, "rate_limit_per_min": 1000, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()["key"]


META = {"prompt_tokens": 12, "completion_tokens": 4, "cost": 0.02}


class _Driver:
    supports_messages = True
    supports_tool_use = True
    supports_streaming = True

    def __init__(self):
        self.seen = {}

    def generate_messages_with_tools(self, messages, tools, options):
        self.seen = {"messages": messages, "tools": tools, "options": options}
        return {
            "text": "Reading.",
            "meta": dict(META),
            "tool_calls": [{"id": "toolu_1", "name": "read_file", "arguments": {"path": "a.py"}}],
            "stop_reason": "tool_use",
        }

    def generate_messages(self, messages, options):
        self.seen = {"messages": messages, "options": options}
        return {"text": "hello", "meta": dict(META)}

    def generate_messages_with_tools_stream(self, messages, tools, options):
        yield TextDelta(text="On it. ")
        yield ToolUseStart(id="toolu_2", name="read_file")
        yield ToolUseStop(id="toolu_2", name="read_file", input={"path": "b.py"})
        yield MessageStop(stop_reason="tool_use", usage=dict(META))


@pytest.fixture
def driver(monkeypatch):
    drv = _Driver()
    seen_models: list[str] = []
    import prompture.drivers as drivers_mod

    def fake(model):
        seen_models.append(model)
        return drv

    monkeypatch.setattr(drivers_mod, "get_driver_for_model", fake)
    drv.models = seen_models
    return drv


TOOLS = [{"name": "read_file", "description": "Read", "input_schema": {"type": "object"}}]


def test_messages_with_tools_via_x_api_key(driver):
    key = _key()
    r = _client().post(
        "/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 256,
            "system": "be brief",
            "tools": TOOLS,
            "messages": [{"role": "user", "content": "open a.py"}],
        },
    )
    assert r.status_code == 200, r.text
    msg = r.json()
    assert msg["type"] == "message"
    assert msg["model"] == "claude-sonnet-4-5"
    assert msg["stop_reason"] == "tool_use"
    assert msg["content"][1] == {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a.py"}}
    assert msg["usage"] == {"input_tokens": 12, "output_tokens": 4}

    assert driver.models == ["claude/claude-sonnet-4-5"]
    assert driver.seen["messages"][0] == {"role": "system", "content": "be brief"}
    assert driver.seen["tools"][0]["function"]["name"] == "read_file"
    assert driver.seen["options"]["max_tokens"] == 256

    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:
        rows = session.exec(select(UsageRecord).where(UsageRecord.status == "ok")).all()
    assert len(rows) == 1
    assert rows[0].endpoint == "/v1/messages"
    assert rows[0].cost_usd == pytest.approx(0.02)


def test_streaming_emits_anthropic_events(driver):
    key = _key()
    r = _client().post(
        "/v1/messages",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "combo/chat", "stream": True, "max_tokens": 64, "tools": TOOLS,
              "messages": [{"role": "user", "content": "go"}]},
    )
    assert r.status_code == 200
    events = [line[len("event: "):] for line in r.text.splitlines() if line.startswith("event: ")]
    assert events[0] == "message_start" and events[-1] == "message_stop"
    assert "content_block_start" in events
    datas = [json.loads(line[len("data: "):]) for line in r.text.splitlines() if line.startswith("data: ")]
    tool_start = next(d for d in datas if d.get("content_block", {}).get("type") == "tool_use")
    assert tool_start["content_block"]["name"] == "read_file"
    delta = next(d for d in datas if d["type"] == "message_delta")
    assert delta["delta"]["stop_reason"] == "tool_use"
    assert driver.models == ["combo/chat"]


def test_allowed_models_enforced(driver):
    key = _key(allowed_models=["combo/chat"])
    r = _client().post(
        "/v1/messages",
        headers={"x-api-key": key},
        json={"model": "claude-opus-4-6", "max_tokens": 8, "messages": [{"role": "user", "content": "x"}]},
    )
    assert r.status_code == 403


def test_count_tokens_estimates(driver):
    key = _key()
    r = _client().post(
        "/v1/messages/count_tokens",
        headers={"x-api-key": key},
        json={"model": "combo/chat", "messages": [{"role": "user", "content": "x" * 400}]},
    )
    assert r.status_code == 200
    assert r.json()["input_tokens"] >= 100


def test_requires_key():
    r = _client().post("/v1/messages", json={"model": "m", "messages": []})
    assert r.status_code == 401

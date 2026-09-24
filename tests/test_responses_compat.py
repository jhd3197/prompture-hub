"""OpenAI Responses API: /v1/responses."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from prompture.agents.live_events import MessageStop, TextDelta, ToolUseStart, ToolUseStop


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


def _key() -> str:
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": "Bearer test-token"},
        json={"name": "codex", "daily_spend_cap_usd": 100.0, "rate_limit_per_min": 1000},
    )
    return r.json()["key"]


class _Driver:
    supports_messages = True
    supports_tool_use = True
    supports_streaming = True

    def generate_messages_with_tools(self, messages, tools, options):
        self.seen = (messages, tools, options)
        return {
            "text": "",
            "meta": {"prompt_tokens": 9, "completion_tokens": 3, "cost": 0.004},
            "tool_calls": [{"id": "call_1", "name": "shell", "arguments": {"cmd": ["ls"]}}],
            "stop_reason": "tool_use",
        }

    def generate_messages_with_tools_stream(self, messages, tools, options):
        yield TextDelta(text="ok ")
        yield ToolUseStart(id="call_2", name="shell")
        yield ToolUseStop(id="call_2", name="shell", input={"cmd": ["pwd"]})
        yield MessageStop(stop_reason="tool_use", usage={"prompt_tokens": 1, "completion_tokens": 1})


@pytest.fixture
def driver(monkeypatch):
    drv = _Driver()
    import prompture.drivers as drivers_mod
    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda m: drv)
    return drv


TOOLS = [{"type": "function", "name": "shell", "parameters": {"type": "object"}}]


def test_non_streaming_function_call(driver):
    key = _key()
    r = _client().post(
        "/v1/responses",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "combo/chat", "instructions": "you are codex", "tools": TOOLS,
              "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "ls"}]}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "response"
    call = body["output"][0]
    assert call["type"] == "function_call" and call["call_id"] == "call_1"
    assert json.loads(call["arguments"]) == {"cmd": ["ls"]}
    assert body["usage"]["total_tokens"] == 12
    messages, tools, _ = driver.seen
    assert messages[0] == {"role": "system", "content": "you are codex"}
    assert tools[0]["function"]["name"] == "shell"


def test_streaming(driver):
    key = _key()
    r = _client().post(
        "/v1/responses",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "combo/chat", "stream": True, "tools": TOOLS, "input": "where am i"},
    )
    assert r.status_code == 200
    types = [line[len("event: "):] for line in r.text.splitlines() if line.startswith("event: ")]
    assert types[0] == "response.created" and types[-1] == "response.completed"
    assert "response.function_call_arguments.done" in types


def test_previous_response_id_rejected(driver):
    key = _key()
    r = _client().post(
        "/v1/responses",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "m", "input": "hi", "previous_response_id": "resp_x"},
    )
    assert r.status_code == 400

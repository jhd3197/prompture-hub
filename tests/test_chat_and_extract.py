"""Non-streaming chat + /v1/extract: response shape and metering.

Prompture drivers return ``{"text", "meta"}`` and ``ask_for_json`` returns
``{"json_object", "json_string", "usage"}``. These tests pin the hub to
those shapes so usage keeps landing in ``UsageRecord`` (spend caps depend
on it).
"""

from __future__ import annotations

import os
import tempfile

import pytest


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


def _create_key(daily_cap: float = 100.0) -> str:
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": "Bearer test-token"},
        json={
            "name": "chat-test",
            "allowed_models": ["stub/model"],
            "daily_spend_cap_usd": daily_cap,
            "rate_limit_per_min": 1000,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["key"]


_META = {
    "prompt_tokens": 7,
    "completion_tokens": 11,
    "total_tokens": 18,
    "cost": 0.5,
    "raw_response": {},
    "model_name": "stub/model",
}


class _MessagesDriver:
    supports_messages = True
    supports_streaming = False

    def __init__(self):
        self.seen_messages = None

    def generate_messages(self, messages, options):
        self.seen_messages = messages
        return {"text": "hi there", "meta": dict(_META)}

    def generate(self, prompt, options):  # pragma: no cover - must not be used
        raise AssertionError("generate() called on a messages-capable driver")


class _PromptOnlyDriver:
    supports_messages = False

    def __init__(self):
        self.seen_prompt = None

    def generate(self, prompt, options):
        self.seen_prompt = prompt
        return {"text": "flat", "meta": dict(_META)}


def _usage_rows():
    from sqlmodel import select

    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:
        return list(session.exec(select(UsageRecord)).all())


def _patch_driver(monkeypatch, driver):
    import prompture.drivers as drivers_mod
    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda _m: driver)


def test_chat_records_usage_from_meta(monkeypatch):
    driver = _MessagesDriver()
    _patch_driver(monkeypatch, driver)
    key = _create_key()

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "stub/model",
            "messages": [
                {"role": "system", "content": "be nice"},
                {"role": "user", "content": "hello"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "hi there"
    assert body["usage"] == {"prompt_tokens": 7, "completion_tokens": 11, "total_tokens": 18}

    # Chat shape preserved — roles are not flattened into one string.
    assert driver.seen_messages == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hello"},
    ]

    rows = [u for u in _usage_rows() if u.status == "ok"]
    assert len(rows) == 1
    assert rows[0].prompt_tokens == 7
    assert rows[0].completion_tokens == 11
    assert rows[0].cost_usd == pytest.approx(0.5)


def test_chat_falls_back_to_prompt_for_prompt_only_driver(monkeypatch):
    driver = _PromptOnlyDriver()
    _patch_driver(monkeypatch, driver)
    key = _create_key()

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "stub/model", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert r.status_code == 200, r.text
    assert driver.seen_prompt == "user: hello"


def test_spend_cap_trips_after_non_streaming_spend(monkeypatch):
    _patch_driver(monkeypatch, _MessagesDriver())
    key = _create_key(daily_cap=0.4)
    payload = {"model": "stub/model", "messages": [{"role": "user", "content": "x"}]}
    headers = {"Authorization": f"Bearer {key}"}

    assert _client().post("/v1/chat/completions", headers=headers, json=payload).status_code == 200
    # First call cost 0.5 > 0.4 cap, so the next one is refused.
    assert _client().post("/v1/chat/completions", headers=headers, json=payload).status_code == 402


def test_stream_rejected_when_driver_cannot_stream(monkeypatch):
    _patch_driver(monkeypatch, _MessagesDriver())
    key = _create_key()

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "stub/model", "stream": True, "messages": [{"role": "user", "content": "x"}]},
    )
    assert r.status_code == 400
    assert "does not support streaming" in r.text


def test_extract_returns_json_object(monkeypatch):
    _patch_driver(monkeypatch, object())

    import prompture.extraction.core as core

    def fake_ask_for_json(**kwargs):
        return {
            "json_string": '{"name": "Ada"}',
            "json_object": {"name": "Ada"},
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 4,
                "total_tokens": 7,
                "cost": 0.01,
                "strategy": "provider_native",
            },
        }

    monkeypatch.setattr(core, "ask_for_json", fake_ask_for_json)
    key = _create_key()

    r = _client().post(
        "/v1/extract",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "stub/model",
            "content": "Ada Lovelace",
            "json_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data"] == {"name": "Ada"}
    assert body["usage"]["total_tokens"] == 7
    assert body["usage"]["strategy"] == "provider_native"


def test_discovery_routes_require_user(monkeypatch):
    # With OAuth configured, anonymous callers must be turned away.
    from prompture_hub import auth

    def deny():
        from fastapi import HTTPException
        raise HTTPException(status_code=401)

    from prompture_hub.main import app
    app.dependency_overrides[auth.require_user] = deny
    try:
        c = _client()
        for path in ("/api/models", "/api/agents", "/api/modalities"):
            assert c.get(path).status_code == 401, path
    finally:
        app.dependency_overrides.clear()

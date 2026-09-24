"""Streaming chat completions: SSE shape, terminator, metering, errors.

We monkey-patch ``prompture.drivers.get_driver_for_model`` so the test
doesn't need a live provider — we just feed the route a stub driver
that yields known events.
"""

from __future__ import annotations

import json
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


def _client(raise_server_exceptions: bool = True):
    from fastapi.testclient import TestClient

    from prompture_hub.main import app
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _create_key(daily_cap: float = 100.0, rate_per_min: int = 1000) -> str:
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": "Bearer test-token"},
        json={
            "name": "stream-test",
            "allowed_models": ["stub/model"],
            "daily_spend_cap_usd": daily_cap,
            "rate_limit_per_min": rate_per_min,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["key"]


class _StreamingStubDriver:
    """Yields delta + done events that mirror Prompture's protocol."""

    def __init__(self, chunks=("Hello", ", ", "world!"), prompt_tok=5, completion_tok=8, cost=0.0012):
        self.chunks = chunks
        self.prompt_tok = prompt_tok
        self.completion_tok = completion_tok
        self.cost = cost

    def generate_messages_stream(self, messages, options):
        for c in self.chunks:
            yield {"type": "delta", "text": c}
        yield {
            "type": "done",
            "text": "".join(self.chunks),
            "meta": {
                "prompt_tokens": self.prompt_tok,
                "completion_tokens": self.completion_tok,
                "total_tokens": self.prompt_tok + self.completion_tok,
                "cost": self.cost,
                "raw_response": {},
                "model_name": "stub/model",
            },
        }


class _NonStreamingStubDriver:
    """Driver that doesn't implement generate_messages_stream."""

    def generate(self, prompt, options):
        return {
            "text": "hi",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
        }


class _RaisingStubDriver:
    def generate_messages_stream(self, messages, options):
        yield {"type": "delta", "text": "partial"}
        raise RuntimeError("upstream blew up")


def _patch_driver(monkeypatch, driver):
    """Make get_driver_for_model return *driver* regardless of model name."""
    import prompture.drivers as p

    def fake(model: str):
        return driver

    monkeypatch.setattr(p, "get_driver_for_model", fake)


def _parse_sse(body: str) -> list[dict | str]:
    """Pull out the JSON payloads (and the [DONE] marker) from a raw SSE body."""
    out: list[dict | str] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            out.append("[DONE]")
        else:
            out.append(json.loads(payload))
    return out


def test_stream_emits_openai_shape_and_done(monkeypatch):
    _patch_driver(monkeypatch, _StreamingStubDriver())
    plaintext = _create_key()

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "model": "stub/model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(r.text)
    # role chunk + 3 content chunks + stop chunk + [DONE]
    assert events[-1] == "[DONE]"
    role_chunk = events[0]
    assert role_chunk["object"] == "chat.completion.chunk"  # type: ignore[index]
    assert role_chunk["choices"][0]["delta"] == {"role": "assistant"}  # type: ignore[index]

    content_chunks = [
        e for e in events
        if isinstance(e, dict) and e["choices"][0]["delta"].get("content")
    ]
    assert [c["choices"][0]["delta"]["content"] for c in content_chunks] == [
        "Hello", ", ", "world!",
    ]

    stop_chunks = [
        e for e in events
        if isinstance(e, dict) and e["choices"][0].get("finish_reason") == "stop"
    ]
    assert len(stop_chunks) == 1


def test_stream_records_usage(monkeypatch):
    _patch_driver(monkeypatch, _StreamingStubDriver(cost=0.0042, prompt_tok=11, completion_tok=22))
    plaintext = _create_key()

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "model": "stub/model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200
    # Drain the body so the generator runs to completion (and _record fires).
    _ = r.text

    rows = _client().get(
        "/admin/usage",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    ok_rows = [r for r in rows if r["status"] == "ok"]
    assert len(ok_rows) == 1
    assert ok_rows[0]["prompt_tokens"] == 11
    assert ok_rows[0]["completion_tokens"] == 22
    assert ok_rows[0]["cost_usd"] == pytest.approx(0.0042, rel=1e-6)


def test_stream_400_when_driver_lacks_streaming(monkeypatch):
    _patch_driver(monkeypatch, _NonStreamingStubDriver())
    plaintext = _create_key()

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "model": "stub/model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 400
    assert "does not support streaming" in r.json()["detail"]


def test_stream_emits_error_then_done_on_driver_failure(monkeypatch):
    _patch_driver(monkeypatch, _RaisingStubDriver())
    plaintext = _create_key()

    r = _client(raise_server_exceptions=False).post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "model": "stub/model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 200  # SSE has already begun streaming when error hits
    events = _parse_sse(r.text)
    assert events[-1] == "[DONE]"
    error_events = [e for e in events if isinstance(e, dict) and "error" in e]
    assert len(error_events) == 1
    assert "upstream blew up" in error_events[0]["error"]["message"]

    rows = _client().get(
        "/admin/usage",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    assert any(r["status"] == "error" for r in rows)


def test_stream_still_enforces_quotas(monkeypatch):
    _patch_driver(monkeypatch, _StreamingStubDriver())
    plaintext = _create_key(daily_cap=0.001, rate_per_min=1000)

    # Seed one usage row that puts us over the cap.
    from datetime import datetime, timezone

    from sqlmodel import select

    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import HubKey, UsageRecord
    with get_session() as session:
        kid = session.exec(select(HubKey).where(HubKey.name == "stream-test")).first().id
        session.add(UsageRecord(
            key_id=kid, model="stub/model", endpoint="/v1/chat/completions",
            cost_usd=0.001, status="ok", timestamp=datetime.now(timezone.utc),
        ))
        session.commit()

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={
            "model": "stub/model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    )
    assert r.status_code == 402, r.text

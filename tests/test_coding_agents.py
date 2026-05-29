"""POST /v1/coding-agents/run — auth, quota, workspace, yolo guardrails.

Prompture's runner is monkey-patched with a stub so tests don't actually
fork subprocesses.
"""

from __future__ import annotations

import json
import os
import tempfile
import types

import pytest


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch, tmp_path):
    db = tmp_path / "hub.db"
    monkeypatch.setenv("HUB_DB_PATH", str(db))
    monkeypatch.setenv("HUB_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("HUB_AGENT_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("HUB_ALLOW_AGENT_YOLO", "false")
    from prompture_hub.settings import get_settings
    get_settings.cache_clear()
    from prompture_hub.storage import db as db_module
    db_module._engine = None
    db_module.init_db()
    yield


def _client(raise_server_exceptions: bool = True):
    from fastapi.testclient import TestClient

    from prompture_hub.main import app
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _new_key(daily_cap: float = 10.0, rate_per_min: int = 1000) -> str:
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": "Bearer test-token"},
        json={
            "name": "agent-test",
            "allowed_models": ["claude"],
            "daily_spend_cap_usd": daily_cap,
            "rate_limit_per_min": rate_per_min,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["key"]


def _stub_run_result(
    *, returncode: int = 0, output: str = "done", cost: float = 0.0042,
    input_tokens: int = 12, output_tokens: int = 34, duration: float = 1.5,
):
    """Build a CodingAgentRunResult-shaped object using SimpleNamespace —
    the route only reads attributes, never imports the dataclass."""
    return types.SimpleNamespace(
        agent="claude",
        command=["claude", "--print", output],
        cwd="/tmp/workspace",
        returncode=returncode,
        output=output,
        duration_seconds=duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        events=[],
    )


def _patch_runner(monkeypatch, fn):
    """Patch both possible import paths so we don't depend on which one
    Prompture exports at the top level."""
    monkeypatch.setattr(
        "prompture_hub.routers.coding_agents.run_coding_agent",
        fn,
        raising=False,
    )
    # Also patch the underlying source so the conditional import in the
    # router falls onto our stub regardless of which path it picked.
    import prompture
    if hasattr(prompture, "run_coding_agent"):
        monkeypatch.setattr(prompture, "run_coding_agent", fn, raising=False)
    import prompture.infra.coding_agents as ca
    monkeypatch.setattr(ca, "run_coding_agent", fn, raising=False)


# ---------------------------------------------------------------- tests


def test_run_requires_hub_key():
    r = _client().post(
        "/v1/coding-agents/run",
        json={"agent": "claude", "task": "hi"},
    )
    assert r.status_code == 401


def test_run_happy_path(monkeypatch):
    pt = _new_key()
    _patch_runner(monkeypatch, lambda *a, **kw: _stub_run_result())

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "Add a docstring to foo()."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["returncode"] == 0
    assert body["usage"]["total_tokens"] == 46
    assert body["usage"]["cost_usd"] == pytest.approx(0.0042, rel=1e-6)


def test_run_records_usage(monkeypatch):
    pt = _new_key()
    _patch_runner(monkeypatch, lambda *a, **kw: _stub_run_result(cost=0.01, input_tokens=5, output_tokens=15))

    _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "explain x"},
    )

    rows = _client().get(
        "/admin/usage",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    runs = [r for r in rows if r["endpoint"] == "/v1/coding-agents/run"]
    assert len(runs) == 1
    assert runs[0]["cost_usd"] == pytest.approx(0.01, rel=1e-6)
    assert runs[0]["total_tokens"] == 20
    assert runs[0]["status"] == "ok"


def test_yolo_refused_by_default(monkeypatch):
    pt = _new_key()
    _patch_runner(monkeypatch, lambda *a, **kw: _stub_run_result())

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "do stuff", "approval_mode": "yolo"},
    )
    assert r.status_code == 403
    assert "yolo" in r.json()["detail"].lower()


def test_yolo_allowed_when_enabled(monkeypatch):
    monkeypatch.setenv("HUB_ALLOW_AGENT_YOLO", "true")
    from prompture_hub.settings import get_settings
    get_settings.cache_clear()

    pt = _new_key()
    _patch_runner(monkeypatch, lambda *a, **kw: _stub_run_result())

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "do stuff", "approval_mode": "yolo"},
    )
    assert r.status_code == 200, r.text


def test_cwd_escape_refused(monkeypatch):
    pt = _new_key()
    _patch_runner(monkeypatch, lambda *a, **kw: _stub_run_result())

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "x", "cwd": "../escape"},
    )
    assert r.status_code == 400
    assert "escapes" in r.json()["detail"].lower()


def test_subpath_under_workspace_is_allowed(monkeypatch):
    pt = _new_key()
    captured: dict[str, object] = {}

    def fake_run(agent, task, *, cwd, **kwargs):
        captured["cwd"] = cwd
        return _stub_run_result()

    _patch_runner(monkeypatch, fake_run)

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "x", "cwd": "subproject"},
    )
    assert r.status_code == 200
    assert str(captured["cwd"]).endswith("subproject")


def test_quotas_still_gate(monkeypatch):
    pt = _new_key(daily_cap=0.001, rate_per_min=1000)
    from datetime import datetime, timezone
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import HubKey, UsageRecord
    from sqlmodel import select
    with get_session() as session:
        kid = session.exec(
            select(HubKey).where(HubKey.name == "agent-test")
        ).first().id
        session.add(UsageRecord(
            key_id=kid, model="x", endpoint="/v1/coding-agents/run",
            cost_usd=0.001, status="ok", timestamp=datetime.now(timezone.utc),
        ))
        session.commit()

    _patch_runner(monkeypatch, lambda *a, **kw: _stub_run_result())

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "x"},
    )
    assert r.status_code == 402


def test_runner_error_returns_502(monkeypatch):
    pt = _new_key()

    def boom(*a, **kw):
        raise RuntimeError("upstream agent went sideways")

    _patch_runner(monkeypatch, boom)

    r = _client(raise_server_exceptions=False).post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "x"},
    )
    assert r.status_code == 502
    assert "sideways" in r.json()["detail"]


# ---------- streaming ----------


def _patch_astream(monkeypatch, events):
    """Patch astream_coding_agent to yield the given event sequence."""
    async def fake_astream(*args, **kwargs):
        for ev in events:
            yield types.SimpleNamespace(**ev)

    import prompture.infra.coding_agents as ca
    monkeypatch.setattr(ca, "astream_coding_agent", fake_astream, raising=False)


def _parse_sse(body: str) -> list:
    out: list = []
    for frame in body.split("\n\n"):
        line = frame.strip()
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        if payload == "[DONE]":
            out.append("[DONE]")
        else:
            out.append(json.loads(payload))
    return out


def test_stream_emits_sse_and_done(monkeypatch):
    pt = _new_key()
    _patch_astream(monkeypatch, [
        {"type": "thinking", "text": "thinking…"},
        {"type": "message",  "text": "Hello world"},
        {"type": "result", "cost_usd": 0.0042,
         "input_tokens": 11, "output_tokens": 22},
    ])

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "hi", "stream": True},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(r.text)
    assert events[-1] == "[DONE]"
    types_seen = [e["type"] for e in events if isinstance(e, dict)]
    assert types_seen == ["thinking", "message", "result"]


def test_stream_records_usage(monkeypatch):
    pt = _new_key()
    _patch_astream(monkeypatch, [
        {"type": "message", "text": "hi"},
        {"type": "result", "cost_usd": 0.01, "input_tokens": 5, "output_tokens": 10},
    ])

    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "claude", "task": "hi", "stream": True},
    )
    assert r.status_code == 200
    _ = r.text  # drain so the generator runs metering

    rows = _client().get(
        "/admin/usage",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    streamed = [r for r in rows if r["endpoint"] == "/v1/coding-agents/run"]
    assert len(streamed) == 1
    assert streamed[0]["cost_usd"] == pytest.approx(0.01, rel=1e-6)
    assert streamed[0]["total_tokens"] == 15


def test_stream_refused_when_agent_lacks_structured_events(monkeypatch):
    pt = _new_key()
    # Aider's spec has parse_events=None, so streaming is refused upstream
    # before astream_coding_agent is even called. No need to patch.
    r = _client().post(
        "/v1/coding-agents/run",
        headers={"Authorization": f"Bearer {pt}"},
        json={"agent": "aider", "task": "x", "stream": True},
    )
    assert r.status_code == 400
    assert "structured" in r.json()["detail"].lower()

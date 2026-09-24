"""Project attribution: X-Project header, key default project, analytics, setup."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
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
    get_settings.cache_clear()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


ADMIN = {"Authorization": "Bearer test-token"}


def _client():
    from fastapi.testclient import TestClient

    from prompture_hub.main import app

    return TestClient(app)


class _Driver:
    supports_messages = True
    supports_streaming = False

    def generate_messages(self, messages, options):
        return {"text": "hi", "meta": {"prompt_tokens": 2, "completion_tokens": 3, "cost": 0.5}}


@pytest.fixture
def stub_driver(monkeypatch):
    import prompture.drivers as drivers_mod

    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda _m: _Driver())


def _key(**extra) -> str:
    payload = {"name": "k", "daily_spend_cap_usd": 100.0, **extra}
    r = _client().post("/admin/keys", headers=ADMIN, json=payload)
    assert r.status_code == 201, r.text
    return r.json()["key"]


def _chat(key: str, project: str | None = None):
    headers = {"Authorization": f"Bearer {key}"}
    if project is not None:
        headers["X-Project"] = project
    return _client().post(
        "/v1/chat/completions",
        headers=headers,
        json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "x"}]},
    )


def _projects() -> list[str | None]:
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:
        return [r.project for r in session.exec(select(UsageRecord).order_by(UsageRecord.id)).all()]


class TestAttribution:
    def test_header_sets_project(self, stub_driver):
        key = _key()
        assert _chat(key, "site-redesign").status_code == 200
        assert _chat(key).status_code == 200
        assert _projects() == ["site-redesign", None]

    def test_key_default_applies_and_header_wins(self, stub_driver):
        key = _key(default_project="billing")
        _chat(key)
        _chat(key, "override")
        assert _projects() == ["billing", "override"]

    def test_labels_are_cleaned(self, stub_driver):
        key = _key()
        _chat(key, "  " + "p" * 150 + "  ")
        _chat(key, "   ")
        assert _projects() == ["p" * 100, None]

    def test_anthropic_and_responses_endpoints_attribute(self, stub_driver):
        key = _key()
        headers = {"x-api-key": key, "X-Project": "cli"}
        r = _client().post(
            "/v1/messages",
            headers=headers,
            json={"model": "openai/gpt-4o-mini", "max_tokens": 10, "messages": [{"role": "user", "content": "x"}]},
        )
        assert r.status_code == 200, r.text
        r = _client().post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {key}", "X-Project": "codex"},
            json={"model": "openai/gpt-4o-mini", "input": "x"},
        )
        assert r.status_code == 200, r.text
        assert _projects() == ["cli", "codex"]

    def test_quota_rejection_is_attributed(self, stub_driver):
        key = _key(daily_spend_cap_usd=0.0)
        r = _chat(key, "tight")
        assert r.status_code == 402

        from prompture_hub.storage.db import get_session
        from prompture_hub.storage.models import UsageRecord

        with get_session() as session:
            row = session.exec(select(UsageRecord)).one()
        assert (row.status, row.project, row.endpoint) == ("quota_exceeded", "tight", "/v1/chat/completions")


class TestAnalytics:
    def test_by_project_and_filter(self, stub_driver):
        key = _key()
        _chat(key, "a")
        _chat(key, "a")
        _chat(key, "b")
        _chat(key)
        data = _client().get("/api/analytics?days=1").json()
        by_project = {row["project"]: row for row in data["by_project"]}
        assert by_project["a"]["requests"] == 2
        assert by_project["a"]["cost_usd"] == pytest.approx(1.0)
        assert by_project[None]["requests"] == 1

        only_b = _client().get("/api/analytics?days=1&project=b").json()
        assert only_b["totals"]["requests"] == 1
        assert only_b["range"]["project"] == "b"

    def test_keys_and_usage_expose_project(self, stub_driver):
        key = _key(default_project="docs")
        _chat(key)
        listed = _client().get("/admin/keys", headers=ADMIN).json()[0]
        assert listed["default_project"] == "docs"
        usage = _client().get("/admin/usage?project=docs", headers=ADMIN).json()
        assert len(usage) == 1
        assert usage[0]["project"] == "docs"

    def test_spa_key_create_accepts_default_project(self):
        r = _client().post("/api/keys", json={"name": "spa", "default_project": " web "})
        assert r.status_code == 201, r.text
        assert r.json()["default_project"] == "web"


class TestSetup:
    def test_claude_code_sends_header_and_writes_folder_settings(self, tmp_path, monkeypatch):
        from prompture_hub.setup_tools import build_plan

        monkeypatch.chdir(tmp_path)
        plan = build_plan("claude-code", base_url="http://h:1", key="ph_k", model="m", project="shop")
        assert plan.env["ANTHROPIC_CUSTOM_HEADERS"] == "X-Project: shop"
        plan.writer()
        local = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
        assert local["env"]["ANTHROPIC_CUSTOM_HEADERS"] == "X-Project: shop"

    def test_codex_and_continue_snippets(self):
        from prompture_hub.setup_tools import build_plan

        codex = build_plan("codex", base_url="http://h:1", key="k", model="m", project="shop")
        assert 'http_headers = { "X-Project" = "shop" }' in codex.snippet
        cont = build_plan("continue", base_url="http://h:1", key="k", model="m", project="shop")
        assert "X-Project: shop" in cont.snippet

    def test_headerless_tools_get_a_key_note(self):
        from prompture_hub.setup_tools import build_plan

        text = build_plan("aider", base_url="http://h:1", key="k", model="m", project="shop").render()
        assert "default project" in text

    def test_dot_means_current_folder(self, tmp_path, monkeypatch):
        from prompture_hub.setup_tools import resolve_project_arg

        folder = tmp_path / "my-app"
        folder.mkdir()
        monkeypatch.chdir(folder)
        assert resolve_project_arg(".") == "my-app"
        assert resolve_project_arg(None) is None

    def test_create_key_with_project(self, capsys):
        from prompture_hub.main import cli

        cli(["setup", "aider", "--create-key", "--project", "shop", "--base-url", "http://h:1"])
        assert "setup:aider:shop" in capsys.readouterr().out

        from prompture_hub.storage.db import get_session
        from prompture_hub.storage.models import HubKey

        with get_session() as session:
            key = session.exec(select(HubKey)).one()
        assert key.default_project == "shop"


def test_setup_without_project_is_unchanged(tmp_path, monkeypatch):
    from prompture_hub.setup_tools import build_plan

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    plan = build_plan("claude-code", base_url="http://h:1", key="k", model="m")
    assert "ANTHROPIC_CUSTOM_HEADERS" not in plan.env
    plan.writer()
    assert (tmp_path / ".claude" / "settings.json").exists()

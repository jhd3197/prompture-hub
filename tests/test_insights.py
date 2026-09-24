"""GET /v1/limits and GET /v1/spend."""

from __future__ import annotations

import os
import tempfile
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
    from prompture.resilience import get_headroom_tracker

    get_headroom_tracker().reset()
    yield
    get_headroom_tracker().reset()
    get_settings.cache_clear()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


def _key(**extra) -> str:
    r = _client().post("/admin/keys", headers=ADMIN, json={"name": "app", "daily_spend_cap_usd": 2.0, **extra})
    assert r.status_code == 201, r.text
    return r.json()["key"]


class _Driver:
    supports_messages = True
    supports_streaming = False

    def generate_messages(self, messages, options):
        now = time.time()
        return {
            "text": "ok",
            "meta": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "cost": 0.5,
                "rate_limits": {
                    "source": "headers",
                    "observed_at": now,
                    "windows": {"tokens": {"limit": 1000, "remaining": 40, "resets_at": now + 60}},
                },
            },
        }


@pytest.fixture
def stub_driver(monkeypatch):
    import prompture.drivers as drivers_mod

    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda _m: _Driver())


def _chat(key: str, project: str | None = None, model: str = "openai/gpt-4o-mini"):
    headers = {"Authorization": f"Bearer {key}"}
    if project:
        headers["X-Project"] = project
    r = _client().post(
        "/v1/chat/completions", headers=headers, json={"model": model, "messages": [{"role": "user", "content": "x"}]}
    )
    assert r.status_code == 200, r.text


class TestLimits:
    def test_key_caps_and_provider_headroom(self, stub_driver, monkeypatch):
        from prompture.infra import accounts

        monkeypatch.setattr(accounts, "get_account_snapshots", lambda **kw: {})
        key = _key(spend_period="week", rate_limit_per_min=30, default_project="web")
        _chat(key)
        body = _client().get("/v1/limits", headers=ADMIN).json()

        [k] = body["keys"]
        assert k["default_project"] == "web"
        assert k["spend"]["period"] == "week"
        assert k["spend"]["spent_usd"] == pytest.approx(0.5)
        assert k["spend"]["fraction_used"] == pytest.approx(0.25)
        assert k["spend"]["resets_at"] is not None
        assert k["rate"] == {"limit_per_min": 30, "calls_last_minute": 1, "source": "hub"}

        [provider] = body["providers"]
        assert provider["target"] == "openai/gpt-4o-mini"
        assert provider["current_headroom"] == pytest.approx(0.04)
        assert provider["current_window"] == "tokens"
        assert body["accounts"] == []

    def test_accounts_are_included_and_optional(self, monkeypatch):
        from prompture.infra import accounts
        from prompture.infra.accounts import AccountSnapshot

        calls = []

        def fake(**kwargs):
            calls.append(kwargs)
            return {"openrouter": AccountSnapshot(source="openrouter", provider="openrouter", balance=4.5)}

        monkeypatch.setattr(accounts, "get_account_snapshots", fake)
        body = _client().get("/v1/limits", headers=ADMIN).json()
        assert body["accounts"][0]["balance"] == 4.5
        assert calls == [{"max_age": 60.0}]

        assert _client().get("/v1/limits?accounts=false", headers=ADMIN).json()["accounts"] is None
        assert len(calls) == 1

    def test_revoked_and_expired_keys_are_hidden(self):
        _key(name="live")
        _key(name="old", expires_in_days=1)
        from datetime import datetime, timedelta, timezone

        from sqlmodel import select

        from prompture_hub.storage.db import get_session
        from prompture_hub.storage.models import HubKey

        with get_session() as session:
            old = session.exec(select(HubKey).where(HubKey.name == "old")).one()
            old.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            session.add(old)
            session.commit()
        names = [k["name"] for k in _client().get("/v1/limits?accounts=false", headers=ADMIN).json()["keys"]]
        assert names == ["live"]

    def test_user_scoped_devices_see_only_their_keys(self, monkeypatch):
        from prompture_hub.companion_auth import Principal, require_read
        from prompture_hub.main import app
        from prompture_hub.settings import get_settings

        _key(name="someone-elses")
        monkeypatch.setenv("HUB_SESSION_SECRET", "s")
        monkeypatch.setenv("HUB_GITHUB_CLIENT_ID", "id")
        monkeypatch.setenv("HUB_GITHUB_CLIENT_SECRET", "secret")
        get_settings.cache_clear()
        app.dependency_overrides[require_read] = lambda: Principal("device", frozenset({"read"}), user_id=99)
        try:
            body = TestClient(app).get("/v1/limits").json()
        finally:
            app.dependency_overrides.clear()
        assert body["keys"] == []
        assert body["providers"] == []
        assert body["accounts"] is None


class TestSpend:
    def test_split_by_project_key_and_model(self, stub_driver):
        a = _key(name="a")
        b = _key(name="b")
        _chat(a, "shop")
        _chat(a, "shop")
        _chat(b, "blog", model="groq/llama")
        _chat(b)
        body = _client().get("/v1/spend", headers=ADMIN).json()
        assert body["period"] == "day"
        assert body["total"]["requests"] == 4
        assert body["total"]["cost_usd"] == pytest.approx(2.0)
        projects = {p["project"]: p for p in body["by_project"]}
        assert projects["shop"]["cost_usd"] == pytest.approx(1.0)
        assert projects[None]["requests"] == 1
        assert [k["name"] for k in body["by_key"]] == ["a", "b"]
        assert {m["model"] for m in body["by_model"]} == {"openai/gpt-4o-mini", "groq/llama"}

    def test_period_validation_and_auth(self):
        assert _client().get("/v1/spend?period=year", headers=ADMIN).status_code == 422
        assert _client().get("/v1/spend?period=month", headers=ADMIN).json()["period"] == "month"
        key = _key()
        assert _client().get("/v1/spend", headers={"Authorization": f"Bearer {key}"}).status_code == 401


def test_info_advertises_limits_and_spend():
    features = _client().get("/v1/companion/info").json()["features"]
    assert features["limits"] == "/v1/limits"
    assert features["spend"] == "/v1/spend"

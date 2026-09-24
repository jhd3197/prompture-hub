"""Key policies (IP allowlist, expiry), route metering, and /api/analytics."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("HUB_DB_PATH", tmp.name)
    monkeypatch.setenv("HUB_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("HUB_TRUST_PROXY_HEADERS", "true")
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


def _client():
    from fastapi.testclient import TestClient

    from prompture_hub.main import app
    return TestClient(app)


ADMIN = {"Authorization": "Bearer test-token"}


def _create_key(**extra):
    payload = {"name": "k", "allowed_models": [], "daily_spend_cap_usd": 100.0, **extra}
    return _client().post("/admin/keys", headers=ADMIN, json=payload)


class _Driver:
    supports_messages = True
    supports_streaming = False

    def generate_messages(self, messages, options):
        return {
            "text": "hi",
            "meta": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "cost": 0.01,
                "route": {
                    "served_by": "b/two",
                    "fallback": True,
                    "attempts": [
                        {"model": "a/one", "outcome": "error"},
                        {"model": "b/two", "outcome": "ok"},
                    ],
                },
            },
        }


def _chat(key: str, ip: str = "10.0.0.5"):
    return _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "X-Forwarded-For": ip},
        json={"model": "combo/test", "messages": [{"role": "user", "content": "x"}]},
    )


@pytest.fixture
def stub_driver(monkeypatch):
    import prompture.drivers as drivers_mod
    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda _m: _Driver())


class TestKeyPolicies:
    def test_ip_allowlist(self, stub_driver):
        r = _create_key(allowed_ips=["10.0.0.0/24", " 192.168.1.7 "])
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["allowed_ips"] == ["10.0.0.0/24", "192.168.1.7/32"]
        key = body["key"]
        assert _chat(key, "10.0.0.5").status_code == 200
        blocked = _chat(key, "8.8.8.8")
        assert blocked.status_code == 403
        assert "IP" in blocked.json()["detail"]

    def test_invalid_cidr_rejected(self):
        r = _create_key(allowed_ips=["not-an-ip"])
        assert r.status_code == 400
        assert "not-an-ip" in r.json()["detail"]

    def test_expired_key_rejected(self, stub_driver):
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        key = _create_key(expires_at=past).json()["key"]
        r = _chat(key)
        assert r.status_code == 401
        assert "expired" in r.json()["detail"]

        listed = _client().get("/admin/keys", headers=ADMIN).json()[0]
        assert listed["expired"] is True
        assert listed["active"] is False

    def test_expires_in_days(self, stub_driver):
        body = _create_key(expires_in_days=30).json()
        exp = datetime.fromisoformat(body["expires_at"])
        assert timedelta(days=29) < exp - datetime.now(timezone.utc) <= timedelta(days=30)
        assert _chat(body["key"]).status_code == 200

    def test_conflicting_expiry(self):
        r = _create_key(expires_in_days=1, expires_at=datetime.now(timezone.utc).isoformat())
        assert r.status_code == 400

    def test_spa_create_accepts_policies(self):
        r = _client().post(
            "/api/keys",
            json={"name": "spa", "allowed_ips": ["::1"], "expires_in_days": 7},
        )
        assert r.status_code == 201, r.text
        assert r.json()["allowed_ips"] == ["::1/128"]
        keys = _client().get("/api/keys").json()
        assert keys[0]["expires_at"] is not None


def test_route_is_recorded_and_analytics_aggregates(stub_driver):
    key = _create_key(name="app-one").json()["key"]
    for _ in range(3):
        assert _chat(key).status_code == 200

    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:
        session.add(UsageRecord(key_id=1, model="a/one", endpoint="/v1/chat/completions", status="error", error="boom"))
        session.add(UsageRecord(key_id=1, model="a/one", endpoint="/v1/chat/completions", status="rate_limited"))
        session.commit()
        rows = session.exec(select(UsageRecord)).all()
    ok_rows = [r for r in rows if r.status == "ok"]
    assert all(r.served_by == "b/two" and r.attempts == 2 for r in ok_rows)

    data = _client().get("/api/analytics?days=7").json()
    t = data["totals"]
    assert t["requests"] == 5
    assert t["errors"] == 1
    assert t["blocked"] == 1
    assert t["error_rate"] == pytest.approx(1 / 4)
    assert t["fallbacks"] == 3
    assert t["cost_usd"] == pytest.approx(0.03)
    assert len(data["by_day"]) == 7
    assert data["by_day"][-1]["requests"] == 5
    assert {m["model"] for m in data["by_model"]} == {"combo/test", "a/one"}
    assert data["by_provider"][0]["provider"] == "b"
    assert data["by_key"][0]["name"] == "app-one"
    assert data["recent_errors"][0]["error"] == "boom"


def test_analytics_validates_days():
    assert _client().get("/api/analytics?days=0").status_code == 422
    assert _client().get("/api/analytics?days=91").status_code == 422

"""Alert rules: evaluation, cooldown, delivery channels and the alert API."""

from __future__ import annotations

import json
import os
import tempfile
import time

import httpx
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
    get_settings.cache_clear()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest.fixture
def delivered(monkeypatch):
    """Run notifications inline and capture the HTTP requests they make."""
    from prompture_hub import alerts

    sent: list[httpx.Request] = []

    class InlinePool:
        def submit(self, fn, *args):
            fn(*args)

    real_client = httpx.Client

    def client(**kwargs):
        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(200)

        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(alerts, "_notify_pool", InlinePool())
    monkeypatch.setattr(alerts.httpx, "Client", client)
    return sent


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


def _key(**extra) -> tuple[int, str]:
    r = _client().post("/admin/keys", headers=ADMIN, json={"name": "app", "daily_spend_cap_usd": 1.0, **extra})
    return r.json()["id"], r.json()["key"]


def _rule(**body) -> dict:
    r = _client().post("/api/alerts/rules", json={"name": "r", **body})
    assert r.status_code == 201, r.text
    return r.json()


class _Driver:
    supports_messages = True
    supports_streaming = False
    meta: dict = {}
    fail = False

    def generate_messages(self, messages, options):
        if self.fail:
            raise RuntimeError("upstream exploded")
        return {"text": "ok", "meta": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.5, **self.meta}}


@pytest.fixture
def driver(monkeypatch):
    import prompture.drivers as drivers_mod

    d = _Driver()
    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda _m: d)
    return d


def _chat(key: str):
    return _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "x"}]},
    )


def _alerts() -> list[dict]:
    return _client().get("/api/alerts").json()


class TestRules:
    def test_defaults_and_validation(self):
        assert _rule(kind="key_spend")["threshold"] == pytest.approx(0.8)
        assert _rule(kind="provider_headroom")["threshold"] == pytest.approx(0.05)
        assert _rule(kind="fallback", threshold=3)["threshold"] is None
        c = _client()
        assert c.post("/api/alerts/rules", json={"name": "x", "kind": "vibes"}).status_code == 400
        assert c.post("/api/alerts/rules", json={"name": "x", "kind": "key_spend", "threshold": 1.5}).status_code == 400
        assert c.post("/api/alerts/rules", json={"name": "x", "kind": "balance_low"}).status_code == 400
        assert c.post("/api/alerts/rules", json={"name": "x", "kind": "error", "key_id": 999}).status_code == 404
        bad_url = {"name": "x", "kind": "error", "webhook_url": "ftp://nope"}
        assert c.post("/api/alerts/rules", json=bad_url).status_code == 422

    def test_update_and_delete(self, driver):
        _, key = _key()
        rule = _rule(kind="error", cooldown_minutes=0)
        patched = _client().patch(f"/api/alerts/rules/{rule['id']}", json={"enabled": False, "name": "quiet"}).json()
        assert (patched["enabled"], patched["name"]) == (False, "quiet")
        driver.fail = True
        _chat(key)
        assert _alerts() == []
        _client().patch(f"/api/alerts/rules/{rule['id']}", json={"enabled": True})
        _chat(key)
        assert len(_alerts()) == 1
        assert _client().delete(f"/api/alerts/rules/{rule['id']}").status_code == 204
        assert _client().get("/api/alerts/rules").json() == []
        assert _alerts() == []


class TestEvaluation:
    def test_key_spend_fires_once_per_cooldown(self, driver):
        key_id, key = _key()
        _rule(kind="key_spend")
        _chat(key)
        assert _alerts() == []  # 50% of the cap
        _chat(key)
        _chat(key)
        [alert] = _alerts()
        assert alert["kind"] == "key_spend"
        assert alert["subject"] == f"key:{key_id}"
        assert alert["value"] == pytest.approx(1.0)
        assert "100%" in alert["message"]

        from prompture_hub.live import get_bus

        fired = [e for e in get_bus().replay(0) if e["type"] == "alert.fired"]
        assert len(fired) == 1 and fired[0]["key_id"] == key_id

    def test_zero_cooldown_repeats(self, driver):
        _, key = _key()
        _rule(kind="key_spend", threshold=0.4, cooldown_minutes=0)
        _chat(key)
        _chat(key)
        assert len(_alerts()) == 2

    def test_rule_scoped_to_another_key_stays_quiet(self, driver):
        other_id, _ = _key(name="other")
        _, key = _key(name="mine")
        _rule(kind="key_spend", threshold=0.1, key_id=other_id)
        _chat(key)
        assert _alerts() == []

    def test_fallback_and_error(self, driver):
        _, key = _key(daily_spend_cap_usd=100.0)
        _rule(kind="fallback")
        _rule(kind="error")
        driver.meta = {
            "route": {
                "served_by": "groq/llama",
                "attempts": [{"model": "openai/gpt-4o-mini", "outcome": "error"}, {"model": "groq/llama", "outcome": "ok"}],
            }
        }
        _chat(key)
        driver.meta = {}
        driver.fail = True
        _chat(key)
        kinds = sorted(a["kind"] for a in _alerts())
        assert kinds == ["error", "fallback"]
        fallback = next(a for a in _alerts() if a["kind"] == "fallback")
        assert "served by groq/llama" in fallback["message"]

    def test_provider_headroom(self, driver):
        _, key = _key(daily_spend_cap_usd=100.0)
        _rule(kind="provider_headroom", threshold=0.1)
        now = time.time()
        driver.meta = {
            "rate_limits": {
                "observed_at": now,
                "windows": {"requests": {"limit": 100, "remaining": 3, "resets_at": now + 30}},
            }
        }
        _chat(key)
        [alert] = _alerts()
        assert alert["subject"] == "openai/gpt-4o-mini"
        assert alert["value"] == pytest.approx(0.03)
        assert "requests window" in alert["message"]

    def test_balance_low_via_limits(self, monkeypatch):
        from prompture.infra import accounts
        from prompture.infra.accounts import AccountSnapshot

        monkeypatch.setattr(
            accounts,
            "get_account_snapshots",
            lambda **kw: {"deepseek": AccountSnapshot(source="deepseek", provider="deepseek", currency="USD", balance=1.5)},
        )
        _rule(kind="balance_low", threshold=5)
        _rule(kind="balance_low", threshold=5, target="openrouter")
        _client().get("/v1/limits", headers=ADMIN)
        [alert] = _alerts()
        assert alert["subject"] == "balance:deepseek"
        assert "1.5 USD" in alert["message"]


class TestDelivery:
    def test_webhook_and_ntfy(self, driver, delivered):
        _, key = _key()
        _rule(
            name="spend",
            kind="key_spend",
            threshold=0.4,
            webhook_url="https://hooks.example.test/hub",
            ntfy_url="https://ntfy.example.test/topic",
        )
        _chat(key)
        webhook, ntfy = delivered
        assert str(webhook.url) == "https://hooks.example.test/hub"
        body = json.loads(webhook.content)
        assert body["type"] == "alert" and body["kind"] == "key_spend" and body["rule"] == "spend"
        assert str(ntfy.url) == "https://ntfy.example.test/topic"
        assert ntfy.headers["Title"] == "prompture-hub: spend"
        assert b"50%" in ntfy.content

    def test_delivery_failure_is_swallowed(self, driver, monkeypatch):
        from prompture_hub import alerts

        class InlinePool:
            def submit(self, fn, *args):
                fn(*args)

        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down", request=request)

        real_client = httpx.Client
        monkeypatch.setattr(alerts, "_notify_pool", InlinePool())
        monkeypatch.setattr(
            alerts.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(unreachable), **kw)
        )
        _, key = _key()
        _rule(kind="key_spend", threshold=0.4, webhook_url="https://hooks.example.test/x")
        assert _chat(key).status_code == 200
        assert len(_alerts()) == 1


class TestCompanionAlerts:
    def _pair(self, scope: str) -> str:
        c = _client()
        start = c.post("/v1/companion/device/code", json={"scope": scope}).json()
        c.post(f"/api/companion/pairings/{start['user_code']}/approve", json={})
        grant = "urn:ietf:params:oauth:grant-type:device_code"
        return c.post("/v1/companion/device/token", json={"grant_type": grant, "device_code": start["device_code"]}).json()[
            "access_token"
        ]

    def test_list_and_ack_scopes(self, driver):
        _, key = _key()
        _rule(kind="key_spend", threshold=0.4)
        _chat(key)
        reader = {"Authorization": f"Bearer {self._pair('read')}"}
        controller = {"Authorization": f"Bearer {self._pair('read control')}"}

        [alert] = _client().get("/v1/alerts?unacknowledged=true", headers=reader).json()
        assert _client().post(f"/v1/alerts/{alert['alert_id']}/ack", headers=reader).status_code == 403
        acked = _client().post(f"/v1/alerts/{alert['alert_id']}/ack", headers=controller).json()
        assert acked["acknowledged_at"] is not None
        assert _client().get("/v1/alerts?unacknowledged=true", headers=reader).json() == []
        assert _client().post("/v1/alerts/999/ack", headers=controller).status_code == 404

    def test_dashboard_ack(self, driver):
        _, key = _key()
        _rule(kind="key_spend", threshold=0.4)
        _chat(key)
        alert_id = _alerts()[0]["alert_id"]
        assert _client().post(f"/api/alerts/{alert_id}/ack").json()["acknowledged_at"] is not None

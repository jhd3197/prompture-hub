"""Key controls: pause/resume, route override, cap and default project."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

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


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


class _Driver:
    supports_messages = True
    supports_streaming = False

    def generate_messages(self, messages, options):
        return {"text": "ok", "meta": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.1}}


@pytest.fixture
def requested_models(monkeypatch):
    import prompture.drivers as drivers_mod

    seen: list[str] = []

    def factory(model):
        seen.append(model)
        return _Driver()

    monkeypatch.setattr(drivers_mod, "get_driver_for_model", factory)
    return seen


def _key(**extra) -> tuple[int, str]:
    r = _client().post("/admin/keys", headers=ADMIN, json={"name": "app", "daily_spend_cap_usd": 5.0, **extra})
    return r.json()["id"], r.json()["key"]


def _chat(key: str, model: str = "openai/gpt-4o-mini"):
    return _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": "x"}]},
    )


def _rows():
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:
        return session.exec(select(UsageRecord).order_by(UsageRecord.id)).all()


def _read_only_token() -> str:
    c = _client()
    start = c.post("/v1/companion/device/code", json={"scope": "read"}).json()
    c.post(f"/api/companion/pairings/{start['user_code']}/approve", json={})
    grant = "urn:ietf:params:oauth:grant-type:device_code"
    return c.post("/v1/companion/device/token", json={"grant_type": grant, "device_code": start["device_code"]}).json()[
        "access_token"
    ]


class TestPause:
    def test_pause_refuses_calls_until_resumed(self, requested_models):
        key_id, key = _key()
        paused = _client().post(f"/v1/keys/{key_id}/pause", headers=ADMIN).json()
        assert paused["paused"] is True and paused["paused_at"] is not None
        refused = _chat(key)
        assert refused.status_code == 403
        assert "paused" in refused.json()["detail"]
        assert _client().get("/api/keys").json()[0]["paused"] is True

        assert _client().post(f"/v1/keys/{key_id}/resume", headers=ADMIN).json()["paused"] is False
        assert _chat(key).status_code == 200

        from prompture_hub.live import get_bus

        updates = [e["changes"] for e in get_bus().replay(0) if e["type"] == "key.updated"]
        assert updates == [{"paused": True}, {"paused": False}]

    def test_pausing_twice_is_quiet(self, requested_models):
        key_id, _ = _key()
        _client().post(f"/v1/keys/{key_id}/pause", headers=ADMIN)
        _client().post(f"/v1/keys/{key_id}/pause", headers=ADMIN)
        from prompture_hub.live import get_bus

        assert len([e for e in get_bus().replay(0) if e["type"] == "key.updated"]) == 1

    def test_needs_control_scope(self):
        key_id, _ = _key()
        reader = {"Authorization": f"Bearer {_read_only_token()}"}
        assert _client().post(f"/v1/keys/{key_id}/pause", headers=reader).status_code == 403
        assert _client().post("/v1/keys/999/pause", headers=ADMIN).status_code == 404


class TestRouteOverride:
    def test_override_serves_calls_and_can_be_cleared(self, requested_models):
        key_id, key = _key()
        r = _client().patch(f"/v1/keys/{key_id}", headers=ADMIN, json={"route_override": "combo/cheap"})
        assert r.json()["route_override"] == "combo/cheap"
        _chat(key, "openai/gpt-4o")
        assert requested_models == ["combo/cheap"]
        row = _rows()[-1]
        assert (row.model, row.served_by) == ("openai/gpt-4o", "combo/cheap")

        from prompture_hub.live import get_bus

        started = [e for e in get_bus().replay(0) if e["type"] == "request.started"][-1]
        assert started["routed_to"] == "combo/cheap"

        _client().patch(f"/v1/keys/{key_id}", headers=ADMIN, json={"route_override": ""})
        _chat(key, "openai/gpt-4o")
        assert requested_models[-1] == "openai/gpt-4o"
        assert _rows()[-1].served_by is None

    def test_override_must_look_like_a_model(self):
        key_id, _ = _key()
        r = _client().patch(f"/v1/keys/{key_id}", headers=ADMIN, json={"route_override": "cheap"})
        assert r.status_code == 400


class TestCapAndProject:
    def test_cap_period_and_project_changes_apply(self, requested_models):
        key_id, key = _key()
        r = _client().patch(
            f"/v1/keys/{key_id}",
            headers=ADMIN,
            json={"daily_spend_cap_usd": 0.5, "spend_period": "month", "default_project": " ops "},
        )
        assert r.status_code == 200, r.text
        assert (r.json()["daily_spend_cap_usd"], r.json()["spend_period"], r.json()["default_project"]) == (
            0.5,
            "month",
            "ops",
        )
        _chat(key)
        assert _rows()[-1].project == "ops"
        [limits] = _client().get("/v1/limits?accounts=false", headers=ADMIN).json()["keys"]
        assert limits["spend"]["period"] == "month"
        assert limits["spend"]["cap_usd"] == 0.5

    def test_invalid_changes(self):
        key_id, _ = _key()
        c = _client()
        assert c.patch(f"/v1/keys/{key_id}", headers=ADMIN, json={"spend_period": "year"}).status_code == 422
        assert c.patch(f"/v1/keys/{key_id}", headers=ADMIN, json={"daily_spend_cap_usd": -1}).status_code == 422
        assert c.patch(f"/v1/keys/{key_id}", headers=ADMIN, json={"daily_spend_cap_usd": None}).status_code == 400

    def test_revoked_keys_cannot_be_changed(self):
        key_id, _ = _key()
        _client().delete(f"/admin/keys/{key_id}", headers=ADMIN)
        assert _client().post(f"/v1/keys/{key_id}/pause", headers=ADMIN).status_code == 404

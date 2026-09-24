"""Companion discovery, device pairing (RFC 8628) and device-token auth."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select

GRANT = "urn:ietf:params:oauth:grant-type:device_code"


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


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


def _start(scope: str = "read", name: str = "Desk") -> dict:
    r = _client().post("/v1/companion/device/code", json={"client_name": name, "scope": scope})
    assert r.status_code == 200, r.text
    return r.json()


def _poll(device_code: str):
    return _client().post("/v1/companion/device/token", json={"grant_type": GRANT, "device_code": device_code})


def _rewind_last_poll(user_code: str) -> None:
    """Pretend the device waited out its polling interval."""
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import DevicePairing

    with get_session() as session:
        row = session.exec(select(DevicePairing).where(DevicePairing.user_code == user_code)).one()
        row.last_poll_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        session.add(row)
        session.commit()


def _pair(scope: str = "read", approve_scopes: list[str] | None = None) -> str:
    start = _start(scope)
    body = {"name": "My laptop"}
    if approve_scopes is not None:
        body["scopes"] = approve_scopes
    assert _client().post(f"/api/companion/pairings/{start['user_code']}/approve", json=body).status_code == 200
    r = _poll(start["device_code"])
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


class TestInfo:
    def test_is_public_and_describes_pairing(self):
        body = _client().get("/v1/companion/info").json()
        assert body["service"] == "prompture-hub"
        assert body["api_version"] == 1
        assert "device_pairing" in body["features"]
        assert body["pairing"]["verification_uri"].endswith("/app/pair")


class TestPairing:
    def test_full_flow(self):
        start = _start("read control")
        assert len(start["user_code"]) == 9 and start["user_code"][4] == "-"
        assert start["verification_uri_complete"].endswith(start["user_code"])
        assert start["interval"] == 5

        pending = _poll(start["device_code"])
        assert pending.status_code == 400
        assert pending.json()["error"] == "authorization_pending"

        info = _client().get(f"/api/companion/pairings/{start['user_code'].lower().replace('-', '')}").json()
        assert info["client_name"] == "Desk"
        assert info["requested_scopes"] == ["read", "control"]

        approved = _client().post(f"/api/companion/pairings/{start['user_code']}/approve", json={"name": "Laptop"})
        assert approved.json() == {"status": "approved", "name": "Laptop", "scopes": ["read", "control"]}

        _rewind_last_poll(start["user_code"])
        token = _poll(start["device_code"])
        assert token.status_code == 200
        body = token.json()
        assert body["access_token"].startswith("phd_")
        assert body["token_type"] == "Bearer"
        assert body["scope"] == "read control"

        again = _poll(start["device_code"])
        assert again.json()["error"] == "invalid_grant"

        devices = _client().get("/api/companion/devices").json()
        assert [(d["name"], d["scopes"], d["active"]) for d in devices] == [("Laptop", ["read", "control"], True)]

    def test_form_encoded_requests(self):
        c = _client()
        start = c.post("/v1/companion/device/code", data={"client_id": "widget", "scope": "read"}).json()
        c.post(f"/api/companion/pairings/{start['user_code']}/approve", json={})
        r = c.post("/v1/companion/device/token", data={"grant_type": GRANT, "device_code": start["device_code"]})
        assert r.status_code == 200, r.text
        assert _client().get("/api/companion/devices").json()[0]["name"] == "widget"

    def test_polling_too_fast_slows_down(self):
        start = _start()
        assert _poll(start["device_code"]).json()["error"] == "authorization_pending"
        slow = _poll(start["device_code"]).json()
        assert slow["error"] == "slow_down"
        assert "10 seconds" in slow["error_description"]

    def test_denied(self):
        start = _start()
        assert _client().post(f"/api/companion/pairings/{start['user_code']}/deny").status_code == 204
        assert _poll(start["device_code"]).json()["error"] == "access_denied"
        assert _client().get(f"/api/companion/pairings/{start['user_code']}").status_code == 404

    def test_expired(self):
        start = _start()
        from prompture_hub.storage.db import get_session
        from prompture_hub.storage.models import DevicePairing

        with get_session() as session:
            row = session.exec(select(DevicePairing)).one()
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.add(row)
            session.commit()
        assert _poll(start["device_code"]).json()["error"] == "expired_token"

    def test_approver_can_narrow_scopes(self):
        token = _pair("read control", approve_scopes=["read"])
        assert token.startswith("phd_")
        assert _client().get("/api/companion/devices").json()[0]["scopes"] == ["read"]

    def test_bad_requests(self):
        c = _client()
        assert c.post("/v1/companion/device/code", json={"scope": "admin"}).status_code == 400
        wrong = c.post("/v1/companion/device/token", json={"grant_type": "password", "device_code": "x"})
        assert wrong.json()["error"] == "unsupported_grant_type"
        assert _poll("nope").json()["error"] == "invalid_grant"

    def test_pending_pairings_are_capped(self, monkeypatch):
        from prompture_hub.routers import companion

        monkeypatch.setattr(companion, "MAX_PENDING", 2)
        _start()
        _start()
        assert _client().post("/v1/companion/device/code", json={}).status_code == 429


class TestDeviceAuth:
    @pytest.fixture
    def app(self):
        from prompture_hub.companion_auth import Principal, require_control, require_read

        app = FastAPI()

        @app.get("/read")
        def read(p: Principal = Depends(require_read)):
            return {"kind": p.kind, "scopes": sorted(p.scopes)}

        @app.get("/control")
        def control(p: Principal = Depends(require_control)):
            return {"kind": p.kind}

        return TestClient(app)

    def test_device_token_scopes(self, app):
        read_only = _pair("read")
        headers = {"Authorization": f"Bearer {read_only}"}
        assert app.get("/read", headers=headers).json() == {"kind": "device", "scopes": ["read"]}
        assert app.get("/control", headers=headers).status_code == 403

        controller = _pair("read control")
        assert app.get("/control", headers={"Authorization": f"Bearer {controller}"}).status_code == 200

    def test_admin_token_and_rejections(self, app):
        assert app.get("/control", headers={"Authorization": "Bearer test-token"}).json() == {"kind": "admin"}
        assert app.get("/read", headers={"Authorization": "Bearer ph_someappkey"}).status_code == 401
        assert app.get("/read", headers={"Authorization": "Bearer phd_unknown"}).status_code == 401

    def test_revoked_device_is_rejected(self, app):
        token = _pair()
        device_id = _client().get("/api/companion/devices").json()[0]["id"]
        assert _client().post(f"/api/companion/devices/{device_id}/revoke").status_code == 204
        assert app.get("/read", headers={"Authorization": f"Bearer {token}"}).status_code == 401

    def test_last_used_is_recorded(self, app):
        token = _pair()
        app.get("/read", headers={"Authorization": f"Bearer {token}"})
        assert _client().get("/api/companion/devices").json()[0]["last_used_at"] is not None

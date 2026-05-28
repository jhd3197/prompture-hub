"""Smoke tests: the app boots, OpenAPI renders, admin gate is wired."""

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
    # Rebuild settings + engine against the new env, then init schema explicitly.
    # TestClient(app) without `with` does NOT trigger FastAPI's lifespan, so we
    # can't rely on it to call init_db() for us.
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


def test_openapi_renders():
    r = _client().get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "prompture-hub"


def test_home_redirects_to_spa():
    r = _client().get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/app/"


def test_admin_requires_token():
    r = _client().get("/admin/keys")
    assert r.status_code == 401


def test_admin_accepts_correct_token():
    r = _client().get("/admin/keys", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_list_key():
    headers = {"Authorization": "Bearer test-token"}
    r = _client().post(
        "/admin/keys",
        headers=headers,
        json={
            "name": "smoke-test",
            "allowed_models": ["ollama/llama3.1:8b"],
            "daily_spend_cap_usd": 0.50,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "smoke-test"
    assert body["key"].startswith("ph_")

    r2 = _client().get("/admin/keys", headers=headers)
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["name"] == "smoke-test"
    assert rows[0]["active"] is True


def test_v1_models_requires_hub_key():
    r = _client().get("/v1/models")
    assert r.status_code == 401

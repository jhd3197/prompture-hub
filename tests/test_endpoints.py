"""Custom OpenAI-compatible endpoints: registration, health checks, history."""

from __future__ import annotations

import os
import tempfile

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
    yield
    from prompture_hub import endpoints

    for name in list(endpoints._profiles()):
        endpoints.unregister(name)
    get_settings.cache_clear()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


def _create(**body) -> dict:
    r = _client().post("/api/endpoints", json={"name": "local-vllm", "base_url": "http://gpu-box:8001/v1/", **body})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def upstream(monkeypatch):
    """Replace the health-check HTTP client with a scripted one."""
    from prompture_hub import endpoints

    state = {"status": 200, "body": {"data": [{"id": "qwen3-32b"}, {"id": "llama-3.3"}]}, "seen": []}
    real = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        state["seen"].append(request)
        if state["status"] is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(state["status"], json=state["body"])

    monkeypatch.setattr(endpoints.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return state


class TestRegistration:
    def test_create_registers_a_routable_profile(self, monkeypatch):
        monkeypatch.setenv("GPU_BOX_KEY", "sk-local")
        body = _create(api_key_env="GPU_BOX_KEY")
        assert body["base_url"] == "http://gpu-box:8001/v1"
        assert body["model_prefix"] == "openai_compatible/local-vllm/"

        from prompture.drivers import get_driver_for_model

        driver = get_driver_for_model("openai_compatible/local-vllm/qwen3-32b")
        assert (driver.endpoint, driver.model, driver.api_key) == ("http://gpu-box:8001/v1", "qwen3-32b", "sk-local")

    def test_validation(self):
        c = _client()
        assert c.post("/api/endpoints", json={"name": "Bad Name", "base_url": "http://x/v1"}).status_code == 400
        assert c.post("/api/endpoints", json={"name": "fireworks", "base_url": "http://x/v1"}).status_code == 409
        assert c.post("/api/endpoints", json={"name": "a", "base_url": "ftp://x"}).status_code == 422
        assert c.post("/api/endpoints", json={"name": "a", "base_url": "http://x", "api_key_env": "sk-123"}).status_code == 422
        _create()
        assert c.post("/api/endpoints", json={"name": "local-vllm", "base_url": "http://y/v1"}).status_code == 409

    def test_update_and_delete(self):
        from prompture_hub import endpoints

        ep = _create()
        r = _client().patch(f"/api/endpoints/{ep['id']}", json={"base_url": "http://other:9000/v1"})
        assert r.json()["base_url"] == "http://other:9000/v1"
        assert endpoints._profiles()["local-vllm"]["endpoint"] == "http://other:9000/v1"
        assert _client().delete(f"/api/endpoints/{ep['id']}").status_code == 204
        assert "local-vllm" not in endpoints._profiles()
        assert _client().get("/api/endpoints").json() == []

    def test_startup_sync(self):
        from prompture_hub import endpoints

        _create()
        endpoints.unregister("local-vllm")
        assert endpoints.sync_all() == 1
        assert "local-vllm" in endpoints._profiles()

    def test_builtin_profiles_survive_unregister(self):
        from prompture_hub import endpoints

        endpoints.unregister("fireworks")
        assert "fireworks" in endpoints._profiles()


class TestHealthCheck:
    def test_online_check_stores_models_and_lists_them(self, upstream, monkeypatch):
        monkeypatch.setenv("GPU_BOX_KEY", "sk-local")
        ep = _create(api_key_env="GPU_BOX_KEY")
        body = _client().post(f"/api/endpoints/{ep['id']}/check").json()
        assert body["last_status"] == "online"
        assert body["models"] == ["llama-3.3", "qwen3-32b"]
        assert body["last_latency_ms"] is not None
        request = upstream["seen"][0]
        assert str(request.url) == "http://gpu-box:8001/v1/models"
        assert request.headers["authorization"] == "Bearer sk-local"

        from prompture.infra import discovery

        monkeypatch.setattr(discovery, "get_available_models", lambda *a, **kw: [])
        key = _client().post("/admin/keys", headers=ADMIN, json={"name": "k"}).json()["key"]
        models = _client().get("/v1/models", headers={"Authorization": f"Bearer {key}"}).json()["data"]
        assert "openai_compatible/local-vllm/qwen3-32b" in {m["id"] for m in models}

    def test_error_and_unreachable_keep_last_models(self, upstream):
        ep = _create()
        _client().post(f"/api/endpoints/{ep['id']}/check")
        upstream["status"] = 401
        body = _client().post(f"/api/endpoints/{ep['id']}/check").json()
        assert (body["last_status"], body["detail"]) == ("error", "HTTP 401")
        assert body["models"] == ["llama-3.3", "qwen3-32b"]
        upstream["status"] = None
        body = _client().post(f"/api/endpoints/{ep['id']}/check").json()
        assert (body["last_status"], body["detail"]) == ("unreachable", "ConnectError")


def test_usage_history_counts_direct_and_routed_calls():
    ep = _create()
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    key_id = _client().post("/admin/keys", headers=ADMIN, json={"name": "k"}).json()["id"]
    with get_session() as session:
        session.add(UsageRecord(key_id=key_id, model="openai_compatible/local-vllm/qwen3-32b", endpoint="/v1/chat/completions", cost_usd=0.1, latency_ms=300))
        session.add(UsageRecord(key_id=key_id, model="combo/local", served_by="openai_compatible/local-vllm/llama-3.3", endpoint="/v1/chat/completions", latency_ms=500))
        session.add(UsageRecord(key_id=key_id, model="openai/gpt-4o", endpoint="/v1/chat/completions"))
        session.commit()
    body = _client().get(f"/api/endpoints/{ep['id']}/usage?days=3").json()
    assert body["totals"]["requests"] == 2
    assert len(body["by_day"]) == 3
    assert {m["model"] for m in body["by_model"]} == {"qwen3-32b", "llama-3.3"}

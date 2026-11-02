"""Cap enforcement hardening: reservations, structured 402/429, unknown pricing, embeddings gating.

Prices come from a patched Prompture rate table (``priced/*`` = $1000 per 1M tokens,
so one token costs $0.001) and drivers are fakes, so nothing depends on live data or today's date.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

AUTH = "test-token"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("HUB_DB_PATH", tmp.name)
    monkeypatch.setenv("HUB_ADMIN_TOKEN", AUTH)
    monkeypatch.setenv("HUB_UNKNOWN_PRICING", "block")
    from prompture_hub import reservations
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    reservations.reset()
    from prompture_hub.storage import db as db_module

    db_module._engine = None
    db_module.init_db()

    def rates(provider, model_id):
        if provider == "priced":
            return {"input": 1000.0, "output": 1000.0}
        if provider == "zero":
            return {"input": 0.0, "output": 0.0}
        return None

    monkeypatch.setattr("prompture.infra.model_rates.get_model_rates", rates)
    yield
    get_settings.cache_clear()
    reservations.reset()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client():
    from fastapi.testclient import TestClient

    from prompture_hub.main import app

    return TestClient(app)


def _key(cap: float = 100.0, rate: int = 1000, models: list[str] | None = None) -> tuple[str, int]:
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": f"Bearer {AUTH}"},
        json={
            "name": "hardening",
            "allowed_models": models if models is not None else [],
            "daily_spend_cap_usd": cap,
            "rate_limit_per_min": rate,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["key"], r.json()["id"]


def _rows():
    from sqlmodel import select

    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:
        return list(session.exec(select(UsageRecord)).all())


def _chat(client, key, model="priced/m", **extra):
    return client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": "hi"}], **extra},
    )


def _meta(cost=1.0):
    return {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": cost, "raw_response": {}}


class _Driver:
    """Non-streaming fake; optionally blocks on *gate* and counts concurrent entries."""

    supports_messages = True
    supports_streaming = True

    def __init__(self, gate: threading.Event | None = None, cost=1.0, fail=False):
        self.gate, self.cost, self.fail = gate, cost, fail
        self.calls = 0
        self.entered = threading.Semaphore(0)

    def generate_messages(self, messages, options):
        self.calls += 1
        self.entered.release()
        if self.gate is not None:
            assert self.gate.wait(10)
        if self.fail:
            raise RuntimeError("upstream down")
        return {"text": "ok", "meta": _meta(self.cost)}

    def generate_messages_stream(self, messages, options):
        self.calls += 1
        self.seen_reserved = []
        yield {"type": "delta", "text": "a"}
        yield {"type": "done", "text": "a", "meta": _meta(self.cost)}


def _patch_driver(monkeypatch, driver):
    import prompture.drivers as p

    monkeypatch.setattr(p, "get_driver_for_model", lambda _m: driver)


def _reserved(key_id):
    from prompture_hub import reservations

    return reservations.reserved_usd(key_id), reservations.in_flight(key_id)


# --- window_resets_at -------------------------------------------------------


@pytest.mark.parametrize(
    ("period", "now", "expected"),
    [
        ("day", datetime(2026, 3, 10, 13, 5, tzinfo=timezone.utc), datetime(2026, 3, 11, tzinfo=timezone.utc)),
        ("day", datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc)),
        ("week", datetime(2026, 3, 11, 9, 0, tzinfo=timezone.utc), datetime(2026, 3, 16, tzinfo=timezone.utc)),
        ("week", datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc), datetime(2026, 3, 16, tzinfo=timezone.utc)),  # Monday
        ("week", datetime(2026, 3, 15, 23, 0, tzinfo=timezone.utc), datetime(2026, 3, 16, tzinfo=timezone.utc)),  # Sunday
        ("week", datetime(2026, 12, 30, 12, 0, tzinfo=timezone.utc), datetime(2027, 1, 4, tzinfo=timezone.utc)),
        ("month", datetime(2026, 3, 31, 23, 0, tzinfo=timezone.utc), datetime(2026, 4, 1, tzinfo=timezone.utc)),
        ("month", datetime(2026, 12, 15, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc)),
        ("month", datetime(2028, 2, 10, tzinfo=timezone.utc), datetime(2028, 3, 1, tzinfo=timezone.utc)),
    ],
)
def test_window_resets_at(period, now, expected):
    from prompture_hub.quotas import window_resets_at

    assert window_resets_at(period, now) == expected


# --- structured errors ------------------------------------------------------


def test_402_cap_reached_body(monkeypatch):
    from prompture_hub import metering
    from prompture_hub.quotas import window_resets_at

    _patch_driver(monkeypatch, _Driver())
    key, kid = _key(cap=1.0)
    metering.record(key_id=kid, model="priced/m", endpoint="/v1/chat/completions", cost=1.0)
    r = _chat(_client(), key)
    assert r.status_code == 402
    body = r.json()
    assert "per day" in body["detail"]
    err = body["error"]
    assert err["code"] == "spend_cap_exceeded"
    assert (err["period"], err["cap_usd"], err["spent_usd"], err["reserved_usd"]) == ("day", 1.0, 1.0, 0.0)
    assert err["window_resets_at"].startswith(window_resets_at("day").strftime("%Y-%m-%dT"))
    assert err["window_start"] < err["window_resets_at"]
    assert any(u.status == "quota_exceeded" for u in _rows())


def test_402_would_exceed_body(monkeypatch):
    _patch_driver(monkeypatch, _Driver())
    key, _ = _key(cap=0.5)  # one request is estimated at ~$1.00
    r = _chat(_client(), key, max_tokens=1000)
    assert r.status_code == 402
    err = r.json()["error"]
    assert err["code"] == "spend_cap_would_exceed"
    assert err["estimated_usd"] == pytest.approx(1.001)
    assert "per day" in r.json()["detail"]


def test_429_body_and_header(monkeypatch):
    _patch_driver(monkeypatch, _Driver())
    key, _ = _key(rate=1)
    c = _client()
    assert _chat(c, key, max_tokens=1).status_code == 200
    r = _chat(c, key, max_tokens=1)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    assert r.json()["error"] == {
        "message": r.json()["detail"], "code": "rate_limit_exceeded", "type": "rate_limit_error",
        "limit_per_min": 1, "in_last_minute": 1, "retry_after_seconds": 60,
    }


def test_anthropic_and_responses_carry_error_object(monkeypatch):
    _patch_driver(monkeypatch, _Driver())
    key, _ = _key(cap=0.5)
    c = _client()
    r = c.post(
        "/v1/messages", headers={"x-api-key": key},
        json={"model": "priced/m", "max_tokens": 1000, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 402 and r.json()["error"]["code"] == "spend_cap_would_exceed"
    r = c.post(
        "/v1/responses", headers={"Authorization": f"Bearer {key}"},
        json={"model": "priced/m", "max_output_tokens": 1000, "input": "hi"},
    )
    assert r.status_code == 402 and r.json()["error"]["code"] == "spend_cap_would_exceed"


# --- reservations -----------------------------------------------------------


def test_concurrent_calls_cannot_overshoot_cap(monkeypatch):
    gate = threading.Event()
    driver = _Driver(gate=gate, cost=1.0)
    _patch_driver(monkeypatch, driver)
    key, kid = _key(cap=3.5)  # headroom for three ~$1.00 estimates, not four
    results: list = []

    def call():
        results.append(_chat(_client(), key, max_tokens=1000))

    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads:
        t.start()
    deadline = time.time() + 10
    while time.time() < deadline and sum(1 for r in results if r.status_code == 402) < 3:
        time.sleep(0.02)
    assert _reserved(kid)[1] == 3  # three admitted and still in flight
    gate.set()
    for t in threads:
        t.join(10)

    assert sorted(r.status_code for r in results) == [200, 200, 200, 402, 402, 402]
    assert {r.json()["error"]["code"] for r in results if r.status_code == 402} == {"spend_cap_would_exceed"}
    assert sum(u.cost_usd for u in _rows()) <= 3.5
    assert _reserved(kid) == (0.0, 0)


def test_in_flight_calls_count_toward_rate_limit(monkeypatch):
    gate = threading.Event()
    driver = _Driver(gate=gate)
    _patch_driver(monkeypatch, driver)
    key, kid = _key(rate=2)
    results: list = []
    threads = [threading.Thread(target=lambda: results.append(_chat(_client(), key, max_tokens=1))) for _ in range(2)]
    for t in threads:
        t.start()
    for _ in range(2):
        assert driver.entered.acquire(timeout=10)
    r = _chat(_client(), key, max_tokens=1)  # both usage rows are still unwritten
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limit_exceeded"
    assert r.json()["error"]["in_last_minute"] == 2
    gate.set()
    for t in threads:
        t.join(10)
    assert [x.status_code for x in results] == [200, 200]


def test_reservation_released_after_success_and_driver_error(monkeypatch):
    key, kid = _key()
    _patch_driver(monkeypatch, _Driver())
    assert _chat(_client(), key).status_code == 200
    assert _reserved(kid) == (0.0, 0)
    _patch_driver(monkeypatch, _Driver(fail=True))
    assert _chat(_client(), key).status_code == 502
    assert _reserved(kid) == (0.0, 0)


def test_streaming_reserves_then_releases(monkeypatch):
    key, kid = _key()
    seen = []

    class _Stream(_Driver):
        def generate_messages_stream(self, messages, options):
            seen.append(_reserved(kid))
            yield from super().generate_messages_stream(messages, options)

    _patch_driver(monkeypatch, _Stream())
    r = _chat(_client(), key, stream=True, max_tokens=100)
    assert r.status_code == 200
    assert seen[0][0] == pytest.approx(0.101) and seen[0][1] == 1
    assert _reserved(kid) == (0.0, 0)


def test_stream_abort_releases(monkeypatch):
    import prompture_hub.routers.openai_compat as oc
    from prompture_hub.routers.openai_compat import ChatCompletionsRequest
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import HubKey

    key, kid = _key()
    with get_session() as session:
        hub_key = session.get(HubKey, kid)
    monkeypatch.setattr(oc, "StreamingResponse", lambda gen, **kw: gen)
    body = ChatCompletionsRequest(model="priced/m", messages=[{"role": "user", "content": "hi"}], stream=True)
    gen = oc._stream_response(_Driver(), body, hub_key, [{"role": "user", "content": "hi"}], {}, None, "priced/m")
    next(gen)
    assert _reserved(kid)[1] == 1
    gen.close()  # client went away mid-stream
    assert _reserved(kid) == (0.0, 0)


def test_release_is_idempotent_and_ttl_expires(monkeypatch):
    from prompture_hub import reservations
    from prompture_hub.quotas import reserve
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import HubKey

    _, kid = _key(cap=1.0)
    with get_session() as session:
        hub_key = session.get(HubKey, kid)
    now = [1000.0]
    monkeypatch.setattr(reservations, "clock", lambda: now[0])
    res = reserve(hub_key, "priced/m", "/x", 0.6)
    assert _reserved(kid) == (0.6, 1)
    res.release()
    res.release()
    assert _reserved(kid) == (0.0, 0)

    reserve(hub_key, "priced/m", "/x", 0.6)  # leaked: never released
    assert _reserved(kid)[1] == 1
    now[0] += 899
    assert _reserved(kid)[1] == 1
    now[0] += 2  # past HUB_RESERVATION_TTL_SECONDS (900)
    assert _reserved(kid) == (0.0, 0)
    reserve(hub_key, "priced/m", "/x", 0.6)  # headroom is back


# --- embeddings -------------------------------------------------------------


class _Emb:
    def __init__(self, cost=0.002, gate=None):
        self.cost = cost

    async def embed(self, texts, options):
        meta = {"total_tokens": 6, "model_name": "priced/emb"}
        if self.cost is not None:
            meta["cost"] = self.cost
        return {"embeddings": [[0.1] for _ in texts], "meta": meta}


def _patch_emb(monkeypatch, emb):
    import prompture.drivers.embedding_registry as reg

    monkeypatch.setattr(reg, "get_async_embedding_driver_for_model", lambda m: emb)


def _embed(client, key, model="priced/emb"):
    return client.post(
        "/v1/embeddings", headers={"Authorization": f"Bearer {key}"}, json={"model": model, "input": ["a", "b"]}
    )


def test_embeddings_cap_402_recorded(monkeypatch):
    _patch_emb(monkeypatch, _Emb())
    key, _ = _key(cap=0.0001)  # even a tiny embedding is estimated above this
    r = _embed(_client(), key)
    assert r.status_code == 402 and r.json()["error"]["code"] == "spend_cap_would_exceed"
    assert [u.status for u in _rows()] == ["quota_exceeded"]
    assert _rows()[0].model == "priced/emb"


def test_embeddings_cap_reached_and_rate_limit_recorded(monkeypatch):
    _patch_emb(monkeypatch, _Emb())
    key, _ = _key(rate=1)
    c = _client()
    assert _embed(c, key).status_code == 200
    r = _embed(c, key)
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    assert "rate_limited" in [u.status for u in _rows()]


def test_embeddings_metered_whitelist_and_pause(monkeypatch):
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import ProviderControl

    _patch_emb(monkeypatch, _Emb(cost=0.002))
    key, kid = _key(models=["priced/emb"])
    c = _client()
    assert _embed(c, key, "priced/other").status_code == 403
    assert _embed(c, key).status_code == 200
    ok = [u for u in _rows() if u.status == "ok"]
    assert len(ok) == 1 and ok[0].cost_usd == pytest.approx(0.002) and ok[0].endpoint == "/v1/embeddings"
    assert _reserved(kid) == (0.0, 0)

    with get_session() as session:
        session.add(ProviderControl(provider="priced", paused_at=datetime.now(timezone.utc)))
        session.commit()
    assert _embed(c, key).status_code == 403


def test_embeddings_cost_computed_when_driver_reports_none(monkeypatch):
    _patch_emb(monkeypatch, _Emb(cost=None))
    key, _ = _key()
    assert _embed(_client(), key).status_code == 200
    assert _rows()[0].cost_usd == pytest.approx(6 * 0.001)  # 6 tokens at $1000/M


def test_embeddings_unknown_pricing_blocked(monkeypatch):
    _patch_emb(monkeypatch, _Emb())
    key, _ = _key()
    r = _embed(_client(), key, "nope/emb")
    assert r.status_code == 402 and r.json()["error"]["code"] == "pricing_unknown"


# --- unknown pricing --------------------------------------------------------


def test_unknown_pricing_blocks_by_default(monkeypatch):
    driver = _Driver()
    _patch_driver(monkeypatch, driver)
    key, _ = _key()
    r = _chat(_client(), key, model="nope/m")
    assert r.status_code == 402
    err = r.json()["error"]
    assert err["code"] == "pricing_unknown" and err["model"] == "nope/m"
    assert "nope/m" in r.json()["detail"] and "HUB_UNKNOWN_PRICING=warn" in r.json()["detail"]
    assert driver.calls == 0
    assert [u.status for u in _rows()] == ["pricing_unknown"]


def test_unknown_pricing_warn_allows_with_header(monkeypatch, caplog):
    monkeypatch.setenv("HUB_UNKNOWN_PRICING", "warn")
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    _patch_driver(monkeypatch, _Driver(cost=0.0))
    key, kid = _key()
    with caplog.at_level(logging.WARNING):
        r = _chat(_client(), key, model="nope/m")
    assert r.status_code == 200 and r.headers["x-hub-cost-warning"] == "unknown-pricing"
    assert "Unknown pricing" in caplog.text
    assert [u.status for u in _rows()] == ["ok"] and _reserved(kid) == (0.0, 0)


def test_unknown_pricing_warn_stream_header(monkeypatch):
    monkeypatch.setenv("HUB_UNKNOWN_PRICING", "warn")
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    _patch_driver(monkeypatch, _Driver())
    key, _ = _key()
    r = _chat(_client(), key, model="nope/m", stream=True)
    assert r.status_code == 200 and r.headers["x-hub-cost-warning"] == "unknown-pricing"


def test_priced_call_has_no_warning_header(monkeypatch):
    _patch_driver(monkeypatch, _Driver())
    key, _ = _key()
    assert "x-hub-cost-warning" not in _chat(_client(), key).headers


@pytest.mark.parametrize("model", ["ollama/llama3", "lmstudio/x", "local_http/y", "zero/free-model"])
def test_free_and_explicit_zero_models_are_known(monkeypatch, model):
    _patch_driver(monkeypatch, _Driver(cost=0.0))
    key, _ = _key()
    r = _chat(_client(), key, model=model)
    assert r.status_code == 200 and "x-hub-cost-warning" not in r.headers


def test_virtual_model_pricing():
    from prompture.resilience import clear_virtual_models, register_combo

    from prompture_hub.pricing import Rates, model_rates

    clear_virtual_models()
    try:
        register_combo("known", ["priced/a", "ollama/b"])
        register_combo("mixed", ["priced/a", "nope/b"])
        assert model_rates("combo/known") == Rates(1000.0, 1000.0)
        assert model_rates("combo/mixed") is None
    finally:
        clear_virtual_models()


def test_zero_cost_for_priced_model_logs_warning(monkeypatch, caplog):
    _patch_driver(monkeypatch, _Driver(cost=0.0))
    key, _ = _key()
    with caplog.at_level(logging.WARNING):
        assert _chat(_client(), key).status_code == 200
    assert "zero cost despite known prices" in caplog.text


def test_unknown_pricing_setting_validated():
    from prompture_hub.settings import HubSettings

    assert HubSettings(unknown_pricing=" WARN ").unknown_pricing == "warn"
    with pytest.raises(ValidationError):
        HubSettings(unknown_pricing="allow")
    s = HubSettings()
    assert (s.default_output_token_estimate, s.reservation_ttl_seconds) == (1024, 900)


def test_limits_endpoint_exposes_reserved(monkeypatch):
    from prompture_hub import reservations

    key, kid = _key()
    reservations.add(kid, 0.25, 900)
    r = _client().get("/v1/limits?accounts=false", headers={"Authorization": f"Bearer {AUTH}"})
    assert r.status_code == 200, r.text
    spend = next(k for k in r.json()["keys"] if k["id"] == kid)["spend"]
    assert spend["reserved_usd"] == 0.25

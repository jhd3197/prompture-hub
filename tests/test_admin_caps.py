"""Admin cap controls: PATCH limits, reset-spend, grant and the window-scoped adjustments behind them."""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from prompture_hub.quotas import _window_start, spend_in_window

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


class _Driver:
    supports_messages = True
    supports_streaming = False

    def generate_messages(self, messages, options):
        return {"text": "ok", "meta": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.1}}


@pytest.fixture(autouse=True)
def _fake_driver(monkeypatch):
    import prompture.drivers as drivers_mod

    monkeypatch.setattr(drivers_mod, "get_driver_for_model", lambda model: _Driver())


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


def _key(**extra) -> tuple[int, str]:
    r = _client().post("/admin/keys", headers=ADMIN, json={"name": "app", "daily_spend_cap_usd": 1.0, **extra})
    return r.json()["id"], r.json()["key"]


def _chat(key: str):
    return _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "openai/gpt-4o-mini", "messages": [{"role": "user", "content": "x"}]},
    )


def _seed_usage(key_id: int, cost: float) -> None:
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:
        session.add(
            UsageRecord(
                key_id=key_id, model="fake/model", endpoint="/v1/chat/completions",
                cost_usd=cost, timestamp=_window_start("day"),
            )
        )
        session.commit()


def _seed_adjustment(key_id: int, amount: float, *, before_window: bool = False) -> None:
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import SpendAdjustment

    ts = _window_start("day") - timedelta(seconds=1) if before_window else _window_start("day")
    with get_session() as session:
        session.add(SpendAdjustment(key_id=key_id, amount_usd=amount, kind="grant", actor_label="t", created_at=ts))
        session.commit()


# ------------------------------------------------------------------ PATCH /admin/keys/{id}


def test_admin_patch_updates_limits_and_returns_list_shape():
    kid, _ = _key()
    r = _client().patch(
        f"/admin/keys/{kid}", headers=ADMIN,
        json={"daily_spend_cap_usd": 7.5, "spend_period": "week", "rate_limit_per_min": 5},
    )
    assert r.status_code == 200, r.text
    listed = next(k for k in _client().get("/admin/keys", headers=ADMIN).json() if k["id"] == kid)
    assert r.json() == listed
    assert (listed["daily_spend_cap_usd"], listed["spend_period"], listed["rate_limit_per_min"]) == (7.5, "week", 5)


@pytest.mark.parametrize(
    "body",
    [
        {"daily_spend_cap_usd": -1},
        {"spend_period": "year"},
        {"rate_limit_per_min": 0},
        {"rate_limit_per_min": "many"},
    ],
)
def test_admin_patch_validation(body):
    kid, _ = _key()
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json=body).status_code in (400, 422)


def test_admin_patch_empty_or_null_body_is_400():
    kid, _ = _key()
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={}).status_code == 400
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": None}).status_code == 400


def test_admin_patch_unknown_and_revoked_are_404():
    kid, _ = _key()
    assert _client().patch("/admin/keys/9999", headers=ADMIN, json={"rate_limit_per_min": 2}).status_code == 404
    _client().delete(f"/admin/keys/{kid}", headers=ADMIN)
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": 2}).status_code == 404


def test_admin_endpoints_require_admin_token():
    kid, key = _key()
    c = _client()
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": f"Bearer {key}"}):
        assert c.patch(f"/admin/keys/{kid}", headers=headers, json={"rate_limit_per_min": 2}).status_code in (401, 403)
        assert c.post(f"/admin/keys/{kid}/reset-spend", headers=headers).status_code in (401, 403)
        assert c.post(f"/admin/keys/{kid}/grant", headers=headers, json={"amount_usd": 1}).status_code in (401, 403)
        assert c.get("/admin/audit", headers=headers).status_code in (401, 403)


def test_admin_patch_publishes_live_event(monkeypatch):
    from prompture_hub.live import get_bus

    kid, _ = _key()
    sent = []
    monkeypatch.setattr(get_bus(), "publish", lambda kind, data: sent.append((kind, data)))
    _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": 9})
    expected = {"key_id": kid, "key_name": "app", "changes": {"rate_limit_per_min": 9}, "by": "admin"}
    assert ("key.updated", expected) in sent


# ------------------------------------------------------------------ rate limit via /v1/keys


def test_v1_patch_rate_limit_takes_effect_on_next_call():
    kid, key = _key(rate_limit_per_min=1000)
    assert _chat(key).status_code == 200
    assert _chat(key).status_code == 200
    r = _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": 1})
    assert r.status_code == 200 and r.json()["rate_limit_per_min"] == 1
    assert _chat(key).status_code == 429
    assert _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": 0}).status_code == 422
    assert _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": None}).status_code == 400


# ------------------------------------------------------------------ reset / grant


def test_reset_spend_lifts_402():
    kid, key = _key()
    _seed_usage(kid, 2.0)
    assert _chat(key).status_code == 402
    r = _client().post(f"/admin/keys/{kid}/reset-spend", headers=ADMIN, json={"reason": "oops"})
    assert r.status_code == 200, r.text
    assert r.json() == {"key_id": kid, "period": "day", "spent_before": 2.0, "spent_after": 0.0, "cap": 1.0}
    assert _chat(key).status_code == 200


def test_reset_spend_with_no_body_and_with_outstanding_grant_lands_on_zero():
    kid, _ = _key()
    _seed_usage(kid, 0.5)
    _seed_adjustment(kid, -3.0)  # effective spend now -2.5
    r = _client().post(f"/admin/keys/{kid}/reset-spend", headers=ADMIN)
    assert r.json()["spent_before"] == -2.5
    assert spend_in_window(kid, "day") == pytest.approx(0.0)


def test_grant_lowers_effective_spend_and_lifts_402_only_when_below_cap():
    kid, key = _key()
    _seed_usage(kid, 2.0)
    r = _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={"amount_usd": 0.5})
    assert r.json()["spent_before"] == 2.0 and r.json()["spent_after"] == 1.5
    assert _chat(key).status_code == 402  # still above the $1 cap
    _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={"amount_usd": 1.0})
    assert spend_in_window(kid, "day") == pytest.approx(0.5)
    assert _chat(key).status_code == 200
    keys = _client().get("/v1/limits", headers=ADMIN).json()["keys"]
    lim = next(k for k in keys if k["id"] == kid)
    assert lim["spend"]["spent_usd"] == pytest.approx(0.6)  # 0.5 plus the 0.1 call


def test_grant_can_exceed_spend_and_goes_negative():
    kid, _ = _key()
    _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={"amount_usd": 5})
    assert spend_in_window(kid, "day") == pytest.approx(-5.0)


@pytest.mark.parametrize("amount", [0, -1])
def test_grant_requires_positive_amount(amount):
    kid, _ = _key()
    assert _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={"amount_usd": amount}).status_code == 422
    assert _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={}).status_code == 422


def test_reset_and_grant_unknown_key_404():
    assert _client().post("/admin/keys/9999/reset-spend", headers=ADMIN).status_code == 404
    assert _client().post("/admin/keys/9999/grant", headers=ADMIN, json={"amount_usd": 1}).status_code == 404


def test_adjustment_from_previous_window_is_ignored():
    kid, key = _key()
    _seed_usage(kid, 2.0)
    _seed_adjustment(kid, -100.0, before_window=True)
    assert spend_in_window(kid, "day") == pytest.approx(2.0)
    assert _chat(key).status_code == 402
    assert _client().get(f"/admin/keys/{kid}/adjustments", headers=ADMIN).json() == []


def test_list_adjustments_shows_current_window():
    kid, _ = _key()
    _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={"amount_usd": 2, "reason": "launch"})
    rows = _client().get(f"/admin/keys/{kid}/adjustments", headers=ADMIN).json()
    assert [(r["kind"], r["amount_usd"], r["reason"], r["actor_label"]) for r in rows] == [
        ("grant", -2.0, "launch", "admin token")
    ]


def test_list_keys_reports_spent_in_window():
    kid, _ = _key()
    _seed_usage(kid, 0.25)
    listed = next(k for k in _client().get("/admin/keys", headers=ADMIN).json() if k["id"] == kid)
    assert listed["spent_in_window"] == 0.25

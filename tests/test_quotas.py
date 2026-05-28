"""Quota enforcement: spend cap (402) and rate limit (429).

These exercise the metered endpoints with a stubbed driver so we don't
need a real LLM. ``check_quotas`` itself is what's under test — the
endpoint just hosts it.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest


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
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client(raise_server_exceptions: bool = True):
    from fastapi.testclient import TestClient

    from prompture_hub.main import app
    # When we exercise /v1/* with a fake model the driver layer raises
    # ValueError — TestClient propagates that by default, masking the
    # response we want to assert on. Tests that go through quotas to the
    # driver layer pass raise_server_exceptions=False.
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _create_key(daily_cap: float = 1.0, rate_per_min: int = 60) -> str:
    """Mint a key via /admin and return its plaintext."""
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": "Bearer test-token"},
        json={
            "name": "quota-test",
            "allowed_models": ["fake/model"],
            "daily_spend_cap_usd": daily_cap,
            "rate_limit_per_min": rate_per_min,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["key"]


def _seed_usage(key_id: int, *, cost: float, count: int, ago_seconds: int = 0) -> None:
    """Insert N synthetic UsageRecord rows for a key."""
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    ts = datetime.now(timezone.utc) - timedelta(seconds=ago_seconds)
    with get_session() as session:
        for _ in range(count):
            session.add(
                UsageRecord(
                    key_id=key_id,
                    model="fake/model",
                    endpoint="/v1/chat/completions",
                    prompt_tokens=10,
                    completion_tokens=20,
                    total_tokens=30,
                    cost_usd=cost,
                    latency_ms=100,
                    status="ok",
                    timestamp=ts,
                )
            )
        session.commit()


def _key_id_for(name: str) -> int:
    from sqlmodel import select
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import HubKey
    with get_session() as session:
        return session.exec(
            select(HubKey).where(HubKey.name == name)
        ).first().id


# ------------------------------------------------------------------ tests


def test_spend_cap_blocks_with_402():
    """Once today's spend hits the cap, /v1/chat/completions returns 402."""
    plaintext = _create_key(daily_cap=0.50, rate_per_min=1000)
    kid = _key_id_for("quota-test")
    _seed_usage(kid, cost=0.50, count=1)  # exactly at the cap

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"model": "fake/model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 402, r.text
    assert "spend cap" in r.json()["detail"].lower()


def test_under_spend_cap_is_not_blocked_by_quota():
    """A key under its cap must NOT be 402'd by the quota check itself.

    The endpoint will still fail because the fake driver doesn't exist,
    but the failure must come from the driver layer, not quotas.
    """
    plaintext = _create_key(daily_cap=10.0, rate_per_min=1000)
    kid = _key_id_for("quota-test")
    _seed_usage(kid, cost=0.10, count=3)  # $0.30 of $10.00

    r = _client(raise_server_exceptions=False).post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"model": "fake/model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code != 402
    assert r.status_code != 429


def test_rate_limit_blocks_with_429_and_retry_after():
    plaintext = _create_key(daily_cap=100.0, rate_per_min=3)
    kid = _key_id_for("quota-test")
    _seed_usage(kid, cost=0.0, count=3)  # exactly at the per-minute limit

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"model": "fake/model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 429, r.text
    assert r.headers.get("Retry-After") == "60"
    assert "rate limit" in r.json()["detail"].lower()


def test_old_calls_do_not_count_toward_rate():
    """Calls older than 60s shouldn't be in the rate-limit window."""
    plaintext = _create_key(daily_cap=100.0, rate_per_min=2)
    kid = _key_id_for("quota-test")
    _seed_usage(kid, cost=0.0, count=10, ago_seconds=120)  # all 2min old

    r = _client(raise_server_exceptions=False).post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"model": "fake/model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code != 429


def test_error_rows_count_toward_rate_but_not_spend():
    """A burst of errors shouldn't bypass the rate limit. They cost $0 though."""
    plaintext = _create_key(daily_cap=0.01, rate_per_min=2)
    kid = _key_id_for("quota-test")
    _seed_usage(kid, cost=0.0, count=2)  # 2 error-style rows (cost 0)

    r = _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"model": "fake/model", "messages": [{"role": "user", "content": "hi"}]},
    )
    # spend is $0 (under $0.01 cap) but rate is 2/min — should be rate-limited.
    assert r.status_code == 429


def test_rejection_is_recorded_in_usage():
    plaintext = _create_key(daily_cap=0.10, rate_per_min=1000)
    kid = _key_id_for("quota-test")
    _seed_usage(kid, cost=0.10, count=1)

    _client().post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {plaintext}"},
        json={"model": "fake/model", "messages": [{"role": "user", "content": "hi"}]},
    )

    rows = _client().get(
        "/admin/usage",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    # The seed row + the rejection row.
    assert any(r["status"] == "quota_exceeded" for r in rows), rows

"""Billing reconciliation: hub spend vs. provider-reported spend, with every provider mocked."""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from prompture.infra.accounts import (
    AccountSnapshot,
    clear_account_cache,
    get_account_sources,
    register_account_source,
)
from prompture.infra.billing import BillingAPIError, BillingReport, BillingRow, BillingScope

from prompture_hub import billing

ADMIN = {"Authorization": "Bearer test-token"}
URL = "/admin/billing/reconciliation"
SECRETS = ("sk-admin-secret", "or-secret-key")
_ENV = ("OPENAI_ADMIN_KEY", "ANTHROPIC_ADMIN_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY")


class FakeBillingClient:
    """Stands in for prompture's BillingClient; ``results`` maps provider -> report | exception."""

    results: dict = {}
    calls: list = []

    def __init__(self, provider, **_):
        if provider not in self.results:
            raise ValueError("An explicit admin_key is required")  # what the real client does without a key
        self.provider = provider

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def get_costs(self, start, end, **_):
        self.calls.append(self.provider)
        result = self.results[self.provider]
        if isinstance(result, Exception):
            raise result
        return result


class FakeSource:
    provider = ""

    def __init__(self, name, snapshot=None):
        self.name = name
        self.provider = name
        self.snapshot = snapshot
        self.fetches = 0

    def is_configured(self):
        return self.snapshot is not None

    def fetch(self, client):
        self.fetches += 1
        if isinstance(self.snapshot, Exception):
            raise self.snapshot
        return self.snapshot


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("HUB_DB_PATH", tmp.name)
    monkeypatch.setenv("HUB_ADMIN_TOKEN", "test-token")
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    from prompture_hub.storage import db as db_module

    db_module._engine = None
    db_module.init_db()

    FakeBillingClient.results = {}
    FakeBillingClient.calls = []
    monkeypatch.setattr(billing, "BillingClient", FakeBillingClient)
    originals = list(get_account_sources())
    for name in ("openrouter", "deepseek", "moonshot"):
        register_account_source(FakeSource(name), replace=True)
    clear_account_cache()
    billing.clear_cache()
    yield
    for source in originals:
        register_account_source(source, replace=True)
    clear_account_cache()
    billing.clear_cache()
    get_settings.cache_clear()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _get(period="month", refresh=False, headers=ADMIN):
    from prompture_hub.main import app

    return TestClient(app).get(URL, params={"period": period, "refresh": refresh}, headers=headers)


def _rows(response):
    assert response.status_code == 200, response.text
    return {r["provider"]: r for r in response.json()["providers"]}


def _seed(model, cost, *, status="ok", period="month", offset=timedelta(minutes=1), served_by=None):
    """Insert a usage row ``offset`` after the start of the current ``period`` window."""
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    ts = billing.window(period)[0] + offset
    with get_session() as session:
        session.add(
            UsageRecord(
                key_id=1, model=model, served_by=served_by, endpoint="/v1/chat/completions",
                cost_usd=cost, status=status, timestamp=ts,
            )
        )
        session.commit()


def _report(provider, amount, *, complete=True, errors=(), warnings=(), currency="USD"):
    start, end = billing.window("month")
    rows = [] if amount is None else [BillingRow(start, end, {}, {}, Decimal(str(amount)), currency)]
    return BillingReport(
        "costs", BillingScope(provider), start, end, rows=rows, complete=complete,
        errors=list(errors), warnings=list(warnings),
    )


def _snapshot(name, **kw):
    register_account_source(
        FakeSource(name, AccountSnapshot(source=name, provider=name, currency="USD", **kw)), replace=True
    )


def test_requires_admin_token():
    assert _get(headers={}).status_code == 401
    assert _get(headers={"Authorization": "Bearer nope"}).status_code == 401


def test_bad_period_is_422():
    assert _get(period="year").status_code == 422


def test_no_credentials_shows_hub_spend_and_hint():
    _seed("openai/gpt-4o", 1.25)
    body = _get().json()
    rows = {r["provider"]: r for r in body["providers"]}
    assert rows["openai"]["status"] == "not_configured"
    assert rows["openai"]["hub_usd"] == 1.25
    assert rows["openai"]["provider_usd"] is None
    assert "OPENAI_ADMIN_KEY" in rows["openai"]["caveats"][0]
    assert rows["anthropic"]["status"] == "not_configured"
    assert body["summary"] == {"mismatches": 0, "errors": 0, "unconfigured": 2}
    assert body["tolerance"] == {"pct": 10, "abs_usd": 0.5}
    assert body["period"] == "month"


def test_ok_within_tolerance():
    _seed("openai/gpt-4o", 100.0)
    FakeBillingClient.results["openai"] = _report("openai", 105.0, warnings=["lagging"])
    row = _rows(_get())["openai"]
    assert (row["status"], row["provider_usd"], row["difference_usd"], row["difference_pct"]) == ("ok", 105.0, 5.0, 5.0)
    assert row["source"] == "openai_billing"
    assert "lagging" in row["caveats"]
    assert any("whole organization" in c for c in row["caveats"])


def test_mismatch_beyond_both_thresholds():
    _seed("openai/gpt-4o", 10.0)
    FakeBillingClient.results["openai"] = _report("openai", 14.0)
    body = _get().json()
    row = {r["provider"]: r for r in body["providers"]}["openai"]
    assert row["status"] == "mismatch" and row["difference_usd"] == 4.0
    assert body["summary"]["mismatches"] == 1


def test_pct_exceeded_but_under_abs_floor_is_ok():
    _seed("openai/gpt-4o", 0.10)
    FakeBillingClient.results["openai"] = _report("openai", 0.30)  # +200%, but only $0.20
    assert _rows(_get())["openai"]["status"] == "ok"


def test_abs_exceeded_but_under_pct_is_ok():
    _seed("openai/gpt-4o", 1000.0)
    FakeBillingClient.results["openai"] = _report("openai", 1002.0)
    assert _rows(_get())["openai"]["status"] == "ok"


def test_provider_spend_with_no_hub_spend_is_mismatch():
    FakeBillingClient.results["openai"] = _report("openai", 3.0)
    row = _rows(_get())["openai"]
    assert row["status"] == "mismatch" and row["difference_pct"] is None


def test_provider_error_is_isolated_and_safe():
    _seed("openai/gpt-4o", 1.0)
    _seed("anthropic/claude-x", 2.0)
    FakeBillingClient.results["openai"] = RuntimeError("boom sk-admin-secret")
    FakeBillingClient.results["anthropic"] = _report("anthropic", 2.0)
    response = _get()
    rows = _rows(response)
    assert rows["openai"]["status"] == "error" and rows["openai"]["error"] == "RuntimeError"
    assert rows["anthropic"]["status"] == "ok"
    assert response.json()["summary"]["errors"] == 1
    assert "sk-admin-secret" not in response.text


def test_billing_api_error_message_is_kept():
    err = BillingAPIError("openai costs report failed (HTTP 403)", _report("openai", None), 403)
    FakeBillingClient.results["openai"] = err
    row = _rows(_get())["openai"]
    assert row["status"] == "error" and "HTTP 403" in row["error"]


def test_incomplete_report_is_not_a_number():
    _seed("openai/gpt-4o", 1.0)
    FakeBillingClient.results["openai"] = _report("openai", 1.0, complete=False)
    FakeBillingClient.results["anthropic"] = _report("anthropic", 1.0, errors=["anthropic costs report failed"])
    rows = _rows(_get())
    assert rows["openai"]["status"] == "not_comparable" and rows["openai"]["provider_usd"] is None
    assert any("incomplete" in c for c in rows["openai"]["caveats"])
    assert rows["anthropic"]["status"] == "error" and rows["anthropic"]["provider_usd"] is None


def test_non_usd_report_is_not_comparable():
    FakeBillingClient.results["openai"] = _report("openai", 5, currency="EUR")
    assert _rows(_get())["openai"]["status"] == "not_comparable"


def test_anthropic_caveat_and_claude_naming():
    _seed("claude/claude-x", 2.0)
    _seed("anthropic/claude-y", 1.0)
    FakeBillingClient.results["anthropic"] = _report("anthropic", 3.0)
    row = _rows(_get())["anthropic"]
    assert row["hub_usd"] == 3.0 and row["status"] == "ok"
    assert any("Priority Tier" in c for c in row["caveats"])


def test_virtual_model_counts_for_serving_provider():
    _seed("combo/cheap", 1.5, served_by="openai/gpt-4o-mini")
    _seed("auto/best", 9.0)  # unattributable: skipped
    assert _rows(_get())["openai"]["hub_usd"] == 1.5


@pytest.mark.parametrize(
    ("period", "field"), [("day", "usage_daily"), ("week", "usage_weekly"), ("month", "usage_monthly")]
)
def test_openrouter_matches_period(period, field):
    _seed("openrouter/some-model", 4.0, period=period)
    _snapshot("openrouter", spent=999.0, period="all_time", details={field: 4.2, "usage_daily": 4.2 if field == "usage_daily" else 77})
    row = _rows(_get(period))["openrouter"]
    assert (row["status"], row["provider_usd"], row["source"]) == ("ok", 4.2, "openrouter")


def test_openrouter_all_time_only_is_not_comparable():
    _seed("openrouter/some-model", 4.0)
    _snapshot("openrouter", spent=999.0, period="all_time", details={"usage_daily": 1.0})
    row = _rows(_get("month"))["openrouter"]
    assert row["status"] == "not_comparable" and row["provider_usd"] is None
    assert any("all-time" in c for c in row["caveats"])


def test_openrouter_fetch_error_is_isolated():
    register_account_source(FakeSource("openrouter", RuntimeError("openrouter returned HTTP 401")), replace=True)
    _seed("openai/gpt-4o", 1.0)
    rows = _rows(_get())
    assert rows["openrouter"]["status"] == "error" and "HTTP 401" in rows["openrouter"]["error"]
    assert rows["openai"]["status"] == "not_configured"


def test_balance_only_providers():
    _snapshot("deepseek", balance=12.5)
    _snapshot("moonshot", balance=3.0)
    _seed("deepseek/deepseek-chat", 0.2)
    rows = _rows(_get())
    assert rows["deepseek"]["status"] == "balance_only" and rows["deepseek"]["balance"] == 12.5
    assert rows["deepseek"]["provider_usd"] is None and rows["deepseek"]["hub_usd"] == 0.2
    assert rows["moonshot"]["status"] == "balance_only" and rows["moonshot"]["balance"] == 3.0


def test_unconfigured_snapshot_provider_with_spend_is_not_configured():
    _seed("deepseek/deepseek-chat", 0.2)
    row = _rows(_get())["deepseek"]
    assert row["status"] == "not_configured" and "DEEPSEEK_API_KEY" in row["caveats"][0]


def test_unsupported_provider():
    _seed("groq/llama", 0.7)
    _seed("openai_compatible/myprofile/m", 0.3)
    rows = _rows(_get())
    assert rows["groq"]["status"] == "unsupported" and rows["groq"]["hub_usd"] == 0.7
    assert rows["myprofile"]["status"] == "unsupported"
    assert rows["groq"]["source"] is None


def test_window_boundaries_and_status_filter():
    FakeBillingClient.results["openai"] = _report("openai", 1.0)
    start, end = billing.window("month")
    _seed("openai/gpt-4o", 1.0)  # inside
    _seed("openai/gpt-4o", 50.0, offset=timedelta(minutes=-1))  # before the window
    for status in ("error", "quota_exceeded", "rate_limited", "pricing_unknown"):
        _seed("openai/gpt-4o", 20.0, status=status)
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import UsageRecord

    with get_session() as session:  # exactly at window_end is excluded (half-open)
        session.add(
            UsageRecord(key_id=1, model="openai/gpt-4o", endpoint="/x", cost_usd=40.0, timestamp=end)
        )
        session.commit()
    body = _get().json()
    assert {r["provider"]: r for r in body["providers"]}["openai"]["hub_usd"] == 1.0
    assert body["window_start"] == start.astimezone(timezone.utc).isoformat()
    assert body["window_end"] == end.isoformat()
    assert start.day == 1 and end.hour == 0 and end > start  # month start .. next UTC midnight


def test_window_is_day_aligned_for_each_period():
    for period in ("day", "week", "month"):
        start, end = billing.window(period)
        assert start.hour == start.minute == end.hour == end.minute == 0 and start < end
        assert _get(period).json()["window_start"].startswith(start.date().isoformat())


def test_cache_and_refresh():
    FakeBillingClient.results["openai"] = _report("openai", 1.0)
    register_account_source(FakeSource("openrouter", AccountSnapshot("openrouter", "openrouter", details={"usage_monthly": 1.0})), replace=True)
    source = next(s for s in get_account_sources() if s.name == "openrouter")
    _get()
    _get()
    assert FakeBillingClient.calls == ["openai"] and source.fetches == 1
    _get(refresh=True)
    assert FakeBillingClient.calls == ["openai", "openai"] and source.fetches == 2
    _get("week")  # different period: separate cache entry
    assert len(FakeBillingClient.calls) == 3


def test_cache_disabled_by_zero_ttl(monkeypatch):
    monkeypatch.setenv("HUB_BILLING_CACHE_SECONDS", "0")
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    FakeBillingClient.results["openai"] = _report("openai", 1.0)
    _get()
    _get()
    assert FakeBillingClient.calls == ["openai", "openai"]


def test_tolerance_is_configurable(monkeypatch):
    monkeypatch.setenv("HUB_BILLING_TOLERANCE_PCT", "1")
    monkeypatch.setenv("HUB_BILLING_TOLERANCE_USD", "0")
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    _seed("openai/gpt-4o", 100.0)
    FakeBillingClient.results["openai"] = _report("openai", 105.0)
    body = _get().json()
    assert body["tolerance"] == {"pct": 1, "abs_usd": 0}
    assert {r["provider"]: r for r in body["providers"]}["openai"]["status"] == "mismatch"


def test_secrets_never_in_response(monkeypatch):
    monkeypatch.setenv("OPENAI_ADMIN_KEY", SECRETS[0])
    monkeypatch.setenv("OPENROUTER_API_KEY", SECRETS[1])
    FakeBillingClient.results["openai"] = RuntimeError(f"leak {SECRETS[0]}")
    _snapshot("openrouter", details={"usage_monthly": 1.0})
    response = _get()
    assert response.status_code == 200
    for secret in SECRETS:
        assert secret not in response.text


def test_dashboard_route_uses_session_auth_not_bearer():
    # Auth is not configured in tests, so require_user falls back to open local mode.
    from prompture_hub.main import app

    FakeBillingClient.results["openai"] = _report("openai", 1.0)
    response = TestClient(app).get("/api/billing/reconciliation?period=week")
    assert response.status_code == 200 and response.json()["period"] == "week"

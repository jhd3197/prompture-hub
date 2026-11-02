"""Billing reconciliation: hub-recorded spend vs. what providers say was billed.

Hub spend is the sum of ``UsageRecord.cost_usd`` over successful calls in a UTC
window, grouped by provider. Provider spend comes from Prompture's
``BillingClient`` (OpenAI / Anthropic organization cost reports, admin keys) and
its account-snapshot registry (OpenRouter spend, DeepSeek / Moonshot balances).
Nothing here raises into the caller: a failing provider only degrades its own row.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from prompture.companion import window_start
from prompture.infra.accounts import get_account_snapshots
from prompture.infra.billing import BillingClient
from sqlalchemy import func
from sqlmodel import select

from .metering import provider_of
from .settings import HubSettings, get_settings
from .storage.db import get_session
from .storage.models import UsageRecord, iso_utc

logger = logging.getLogger("prompture_hub.billing")

PERIODS = ("day", "week", "month")

# Prompture names Anthropic "claude" in its account registry; the hub says "anthropic".
_ALIASES = {"claude": "anthropic"}
_ADMIN_KEY_ENV = {"openai": "OPENAI_ADMIN_KEY", "anthropic": "ANTHROPIC_ADMIN_KEY"}
_KEY_ENV = {"openrouter": "OPENROUTER_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "moonshot": "MOONSHOT_API_KEY"}
_BALANCE_ONLY = ("deepseek", "moonshot")
_OPENROUTER_FIELD = {"day": "usage_daily", "week": "usage_weekly", "month": "usage_monthly"}
_ORDER = ("openai", "anthropic", "openrouter", "deepseek", "moonshot")

_COMMON_CAVEATS = (
    "Provider totals cover the whole organization or key: activity outside the hub counts too.",
    "Billing data can lag by hours; recent calls may not be reflected yet.",
)

_cache: dict[tuple[str, float, float], tuple[float, dict[str, Any]]] = {}


def clear_cache() -> None:
    _cache.clear()


def window(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    """UTC ``[start, end)``: the period start to the next UTC midnight (day-aligned for provider buckets)."""
    now = now or datetime.now(timezone.utc)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return window_start(period, now), end


def hub_spend(start: datetime, end: datetime) -> dict[str, float]:
    """Successful-call cost per provider in the window. Virtual models count where they were served."""
    stmt = (
        select(UsageRecord.served_by, UsageRecord.model, func.sum(UsageRecord.cost_usd))
        .where(UsageRecord.status == "ok", UsageRecord.timestamp >= start, UsageRecord.timestamp < end)
        .group_by(UsageRecord.served_by, UsageRecord.model)
    )
    with get_session() as session:
        rows = session.exec(stmt).all()
    out: dict[str, float] = {}
    for served_by, model, cost in rows:
        provider = provider_of(served_by or model)
        if provider:
            provider = _ALIASES.get(provider, provider)
            out[provider] = out.get(provider, 0.0) + float(cost or 0.0)
    return out


def _row(provider: str, status: str, hub: float, source: str | None, **kw: Any) -> dict[str, Any]:
    caveats = list(kw.pop("caveats", []))
    return {
        "provider": provider,
        "status": status,
        "hub_usd": round(hub, 6),
        "provider_usd": None,
        "difference_usd": None,
        "difference_pct": None,
        "balance": None,
        "currency": "USD",
        "source": source,
        "caveats": caveats,
        "error": None,
        "fetched_at": None,
        **kw,
    }


def _compare(row: dict[str, Any], provider_usd: float, s: HubSettings) -> dict[str, Any]:
    hub = row["hub_usd"]
    diff = provider_usd - hub
    pct = diff / hub * 100 if hub > 0 else None
    # A mismatch must exceed BOTH thresholds; no hub baseline means any amount over the abs floor.
    over_pct = pct is None or abs(pct) > s.billing_tolerance_pct
    row.update(
        provider_usd=round(provider_usd, 6),
        difference_usd=round(diff, 6),
        difference_pct=None if pct is None else round(pct, 2),
        status="mismatch" if abs(diff) > s.billing_tolerance_usd and over_pct else "ok",
    )
    return row


def _org_costs(provider: str, hub: float, start: datetime, end: datetime, s: HubSettings) -> dict[str, Any]:
    source = f"{provider}_billing"
    env = _ADMIN_KEY_ENV[provider]
    caveats = list(_COMMON_CAVEATS)
    if provider == "anthropic":
        caveats.append("Anthropic's cost report excludes Priority Tier costs.")
    try:
        client = BillingClient(provider, timeout=20.0)  # type: ignore[arg-type]
    except ValueError:  # no admin key configured
        return _row(provider, "not_configured", hub, source, caveats=[f"Set {env} to compare.", *caveats])
    try:
        with client:
            report = client.get_costs(start, end)
    except Exception as exc:
        # BillingAPIError messages are secret-free by construction; anything else: class name only.
        msg = str(exc) if type(exc).__name__ == "BillingAPIError" else type(exc).__name__
        logger.warning("%s billing fetch failed: %s", provider, msg)
        return _row(provider, "error", hub, source, caveats=caveats, error=msg[:200])

    caveats += [w for w in report.warnings if w not in caveats]
    fetched = iso_utc(report.fetched_at)
    if report.errors:
        return _row(provider, "error", hub, source, caveats=caveats, error="; ".join(report.errors)[:200], fetched_at=fetched)
    if not report.complete:
        caveats.append("Provider report was incomplete, so no total is shown.")
        return _row(provider, "not_comparable", hub, source, caveats=caveats, fetched_at=fetched)
    totals = report.totals
    if set(totals) - {"USD"}:
        caveats.append(f"Provider billed in {', '.join(sorted(totals))}; only USD is compared.")
        return _row(provider, "not_comparable", hub, source, caveats=caveats, fetched_at=fetched)
    total = float(totals.get("USD", Decimal(0)))
    return _compare(_row(provider, "ok", hub, source, caveats=caveats, fetched_at=fetched), total, s)


def _snapshot_row(provider: str, hub: float, snap: Any, period: str, s: HubSettings) -> dict[str, Any]:
    fetched = iso_utc(datetime.fromtimestamp(snap.observed_at, timezone.utc))
    kw: dict[str, Any] = {"currency": snap.currency or "USD", "fetched_at": fetched}
    if snap.error:
        return _row(provider, "error", hub, snap.source, error=snap.error[:200], caveats=list(_COMMON_CAVEATS), **kw)
    if provider in _BALANCE_ONLY:
        note = f"{provider} exposes only an account balance, not spend, so there is nothing to reconcile."
        return _row(provider, "balance_only", hub, snap.source, balance=snap.balance, caveats=[note], **kw)
    # OpenRouter: /key reports usage for the configured key only.
    caveats = [*_COMMON_CAVEATS, "OpenRouter figures cover only the configured API key."]
    spent = (snap.details or {}).get(_OPENROUTER_FIELD[period])
    if not isinstance(spent, (int, float)) or isinstance(spent, bool):
        caveats.append(f"No {period} usage reported (only all-time spend), which is not comparable to this window.")
        return _row(provider, "not_comparable", hub, snap.source, caveats=caveats, **kw)
    return _compare(_row(provider, "ok", hub, snap.source, caveats=caveats, **kw), float(spent), s)


def _snapshot_rows(
    hub: dict[str, float], period: str, s: HubSettings
) -> dict[str, dict[str, Any]]:
    try:
        snaps = get_account_snapshots(["openrouter", *_BALANCE_ONLY], max_age=0, timeout=20.0)
    except Exception as exc:  # the registry should not raise, but never take the endpoint down
        logger.warning("account snapshot lookup failed: %s", type(exc).__name__)
        snaps = {}
    rows: dict[str, dict[str, Any]] = {}
    for name in ("openrouter", *_BALANCE_ONLY):
        snap = next((x for x in snaps.values() if _ALIASES.get(x.provider, x.provider) == name), None)
        if snap is not None:
            try:
                rows[name] = _snapshot_row(name, hub.get(name, 0.0), snap, period, s)
            except Exception as exc:
                rows[name] = _row(name, "error", hub.get(name, 0.0), snap.source, error=type(exc).__name__)
        elif hub.get(name):
            rows[name] = _row(
                name, "not_configured", hub[name], name, caveats=[f"Set {_KEY_ENV[name]} to compare."]
            )
    return rows


def build_reconciliation(period: str, s: HubSettings) -> dict[str, Any]:
    start, end = window(period)
    hub = hub_spend(start, end)
    # Blocking HTTP: fetch the two org reports and the snapshots concurrently.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {p: pool.submit(_org_costs, p, hub.get(p, 0.0), start, end, s) for p in _ADMIN_KEY_ENV}
        snaps = pool.submit(_snapshot_rows, hub, period, s)
        rows = {p: f.result() for p, f in futures.items()}
        rows.update(snaps.result())
    for p, spent in hub.items():
        if p not in rows:
            note = f"No billing source is available for {p}; the hub figure is not verified."
            rows[p] = _row(p, "unsupported", spent, None, caveats=[note])
    ordered = sorted(rows.values(), key=lambda r: (_ORDER.index(r["provider"]) if r["provider"] in _ORDER else 99, r["provider"]))
    count = lambda st: sum(r["status"] == st for r in ordered)  # noqa: E731
    return {
        "period": period,
        "window_start": iso_utc(start),
        "window_end": iso_utc(end),
        "generated_at": iso_utc(datetime.now(timezone.utc)),
        "tolerance": {"pct": s.billing_tolerance_pct, "abs_usd": s.billing_tolerance_usd},
        "providers": ordered,
        "summary": {"mismatches": count("mismatch"), "errors": count("error"), "unconfigured": count("not_configured")},
    }


def reconciliation(period: str, refresh: bool = False) -> dict[str, Any]:
    s = get_settings()
    key = (period, s.billing_tolerance_pct, s.billing_tolerance_usd)
    hit = _cache.get(key)
    if not refresh and hit and time.monotonic() - hit[0] < s.billing_cache_seconds:
        return hit[1]
    payload = build_reconciliation(period, s)
    _cache[key] = (time.monotonic(), payload)
    return payload

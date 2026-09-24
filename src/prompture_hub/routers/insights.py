"""Read-only views a companion polls: headroom and spend.

- ``GET /v1/limits`` — how much room is left: each hub key's spend cap and
  rate limit, each provider target's rate-limit windows (as last reported by
  the provider), and account balances from documented provider endpoints.
- ``GET /v1/spend`` — what the current UTC day / week / month has cost, split
  by project, key and model.

Both take a device token (``read`` scope), the admin token, or a dashboard
session. Every figure carries where it came from; nothing is extrapolated.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from sqlmodel import select

from ..companion_auth import Principal, require_read, visible_key_ids
from ..metering import paused_providers
from ..policies import is_expired
from ..quotas import _window_start, calls_in_last_minute, spend_in_window, window_end
from ..storage.db import get_session
from ..storage.models import HubKey, UsageRecord, iso_utc

router = APIRouter()


def _visible_keys(principal: Principal) -> list[HubKey]:
    key_ids = visible_key_ids(principal)
    with get_session() as session:
        stmt = select(HubKey).where(HubKey.revoked_at.is_(None)).order_by(HubKey.created_at, HubKey.id)
        if key_ids is not None:
            stmt = stmt.where(HubKey.id.in_(key_ids or [-1]))
        return [k for k in session.exec(stmt).all() if not is_expired(k)]


def _key_limits(key: HubKey) -> dict[str, Any]:
    period = (key.spend_period or "day").lower()
    spent = spend_in_window(key.id, period)
    cap = key.daily_spend_cap_usd
    return {
        "id": key.id,
        "name": key.name,
        "default_project": key.default_project,
        "paused": key.paused_at is not None,
        "route_override": key.route_override,
        "spend": {
            "period": period,
            "cap_usd": cap,
            "spent_usd": round(spent, 6),
            "fraction_used": round(spent / cap, 4) if cap > 0 else None,
            "resets_at": iso_utc(window_end(period)),
            "source": "hub",
        },
        "rate": {
            "limit_per_min": key.rate_limit_per_min,
            "calls_last_minute": calls_in_last_minute(key.id),
            "source": "hub",
        },
    }


def _provider_limits() -> list[dict[str, Any]] | None:
    try:
        from prompture.resilience import get_headroom_tracker
    except ImportError:
        return None
    return [{"target": label, **data} for label, data in sorted(get_headroom_tracker().snapshot().items())]


def _account_limits(max_age: float) -> list[dict[str, Any]] | None:
    try:
        from prompture.infra.accounts import get_account_snapshots
    except ImportError:
        return None
    return [snap.to_dict() for snap in get_account_snapshots(max_age=max_age).values()]


@router.get("/limits")
async def limits(
    principal: Principal = Depends(require_read),
    accounts: bool = Query(default=True, description="Include provider account balances (cached ~60s)."),
) -> dict[str, Any]:
    """Headroom across hub keys, provider rate limits and provider accounts.

    ``providers`` / ``accounts`` are ``null`` when the installed Prompture
    predates that capability, and ``[]`` when there is simply nothing yet.
    """
    keys = await run_in_threadpool(lambda: [_key_limits(k) for k in _visible_keys(principal)])
    body: dict[str, Any] = {
        "generated_at": iso_utc(datetime.now(timezone.utc)),
        "keys": keys,
        "providers": _provider_limits(),
        "accounts": None,
        "paused_providers": sorted(paused_providers()),
    }
    # Provider rate limits and balances describe the hub's own upstream
    # credentials, so they are shown only to callers who can see every key.
    if not principal.sees_everything:
        body["providers"] = []
        return body
    if accounts:
        body["accounts"] = await run_in_threadpool(_account_limits, 60.0)
        if body["accounts"]:
            from ..alerts import evaluate_accounts

            await run_in_threadpool(evaluate_accounts, body["accounts"])
    return body


def _bucket() -> dict[str, Any]:
    return {"requests": 0, "cost_usd": 0.0, "tokens": 0, "errors": 0}


def _add(bucket: dict[str, Any], row: UsageRecord) -> None:
    bucket["requests"] += 1
    bucket["cost_usd"] += row.cost_usd or 0.0
    bucket["tokens"] += row.total_tokens or 0
    if row.status == "error":
        bucket["errors"] += 1


def _ranked(buckets: dict[Any, dict[str, Any]], label: str) -> list[dict[str, Any]]:
    rows = [{label: k, **v, "cost_usd": round(v["cost_usd"], 6)} for k, v in buckets.items()]
    return sorted(rows, key=lambda r: (-r["cost_usd"], -r["requests"]))


@router.get("/spend")
def spend(
    principal: Principal = Depends(require_read),
    period: str = Query(default="day", pattern="^(day|week|month)$"),
) -> dict[str, Any]:
    """Spend in the current UTC period, split by project, key and model."""
    start = _window_start(period)
    key_ids = visible_key_ids(principal)
    with get_session() as session:
        stmt = select(UsageRecord).where(UsageRecord.timestamp >= start)
        if key_ids is not None:
            stmt = stmt.where(UsageRecord.key_id.in_(key_ids or [-1]))
        rows = session.exec(stmt).all()
        names = {k.id: k.name for k in session.exec(select(HubKey)).all()}

    total = _bucket()
    by_project: dict[str | None, dict[str, Any]] = defaultdict(_bucket)
    by_key: dict[int, dict[str, Any]] = defaultdict(_bucket)
    by_model: dict[str, dict[str, Any]] = defaultdict(_bucket)
    for row in rows:
        _add(total, row)
        _add(by_project[row.project], row)
        _add(by_key[row.key_id], row)
        _add(by_model[row.served_by or row.model], row)

    keys = _ranked(by_key, "key_id")
    for item in keys:
        item["name"] = names.get(item["key_id"], f"key {item['key_id']}")
    total["cost_usd"] = round(total["cost_usd"], 6)
    return {
        "period": period,
        "start": iso_utc(start),
        "resets_at": iso_utc(window_end(period)),
        "total": total,
        "by_project": _ranked(by_project, "project"),
        "by_key": keys,
        "by_model": _ranked(by_model, "model"),
    }

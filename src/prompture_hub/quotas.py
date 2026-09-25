"""Pre-call enforcement of a HubKey's spend cap and rate limit.

Both checks are DB-backed against :class:`UsageRecord`, so they work across
multiple uvicorn workers and survive restarts. They're called BEFORE the
upstream provider request so an over-quota key never burns real credits.

Semantics
---------
- Spend cap is measured against the current UTC day. Any record whose
  ``timestamp`` falls in ``[utc_midnight, now]`` contributes its
  ``cost_usd`` to the running total. Error rows have ``cost_usd == 0`` so
  they don't bump the spend total.
- Rate limit is a fixed 60-second sliding window — every record in
  ``[now - 60s, now]`` counts toward ``rate_limit_per_min``, including
  errors (a flood of failures shouldn't bypass the limit).
- 402 Payment Required is used for the spend cap, 429 Too Many Requests
  for the rate limit (with a ``Retry-After`` header).

The check is intentionally "reactive": we don't try to pre-estimate the
cost of the call being attempted. If the cap is `$1.00/day` and the key
is at `$0.99`, a request that ends up costing `$0.05` will go through —
the next request will see `$1.04` and be rejected. This matches what
most metered SaaS products do and keeps the math obvious.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from prompture.companion import window_start
from sqlalchemy import func
from sqlmodel import select

from .auth import require_hub_key
from .storage.db import get_session
from .storage.models import HubKey, UsageRecord

# Errors recorded for over-quota requests use these status strings so the
# admin dashboard can distinguish them from real provider errors.
STATUS_QUOTA_EXCEEDED = "quota_exceeded"
STATUS_RATE_LIMITED = "rate_limited"


def _window_start(period: str) -> datetime:
    """First UTC instant of the current cap window: day, week (Monday) or month."""
    return window_start(period)


def spend_in_window(key_id: int, period: str) -> float:
    """Public alias used by the limits endpoint and alert rules."""
    return _spend_in_window(key_id, period)


def calls_in_last_minute(key_id: int) -> int:
    return _calls_in_last_minute(key_id)


def _period_label(period: str) -> str:
    p = (period or "day").lower()
    if p == "week":
        return "this UTC week (Mon–Sun)"
    if p == "month":
        return "this UTC month"
    return "the rest of the UTC day"


def _spend_in_window(key_id: int, period: str) -> float:
    """Sum cost_usd inside the cap window for ``period``."""
    window_start = _window_start(period)
    with get_session() as session:
        total = session.exec(
            select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0))
            .where(UsageRecord.key_id == key_id)
            .where(UsageRecord.timestamp >= window_start)
        ).one()
    return float(total or 0.0)


def _calls_in_last_minute(key_id: int) -> int:
    window_start = datetime.now(timezone.utc) - timedelta(seconds=60)
    with get_session() as session:
        count = session.exec(
            select(func.count(UsageRecord.id))
            .where(UsageRecord.key_id == key_id)
            .where(UsageRecord.timestamp >= window_start)
        ).one()
    return int(count or 0)


def _record_rejection(key_id: int, endpoint: str, model: str, reason: str, project: str | None = None) -> None:
    """Stamp a quota_exceeded / rate_limited row so the dashboard sees the rejection."""
    from .metering import record

    record(key_id=key_id, model=model, endpoint=endpoint, status=reason, error=reason, project=project)


def check_quotas(key: HubKey, endpoint: str = "", model: str = "", project: str | None = None) -> None:
    """Raise an HTTPException if the key has tripped its spend or rate quota.

    Spend is checked first; over-cap requests can't bypass it by being slow.
    """
    period = getattr(key, "spend_period", "day") or "day"
    spent = _spend_in_window(key.id, period)
    if spent >= key.daily_spend_cap_usd:
        _record_rejection(key.id, endpoint, model, STATUS_QUOTA_EXCEEDED, project)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Spend cap of ${key.daily_spend_cap_usd:.2f} per {period} "
                f"reached (${spent:.4f} spent so far). "
                f"Refusing calls for {_period_label(period)}."
            ),
        )

    calls = _calls_in_last_minute(key.id)
    if calls >= key.rate_limit_per_min:
        _record_rejection(key.id, endpoint, model, STATUS_RATE_LIMITED, project)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit of {key.rate_limit_per_min} requests/minute exceeded "
                f"({calls} in the last 60 seconds)."
            ),
            headers={"Retry-After": "60"},
        )


async def enforce_quotas(request: Request, key: HubKey = Depends(require_hub_key)) -> HubKey:
    """Dependency for /v1/* endpoints that should be quota-gated.

    Note: the model isn't known here (it's in the request body), so the
    rejection row gets ``model=""``. The endpoint-specific handler can
    re-check after parsing the body if you want per-model attribution —
    most callers don't need that.
    """
    from .metering import resolve_project

    check_quotas(key, endpoint=request.url.path, project=resolve_project(request, key))
    return key

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

from fastapi import Depends, HTTPException, status
from sqlalchemy import func
from sqlmodel import select

from .auth import require_hub_key
from .storage.db import get_session
from .storage.models import HubKey, UsageRecord

# Errors recorded for over-quota requests use these status strings so the
# admin dashboard can distinguish them from real provider errors.
STATUS_QUOTA_EXCEEDED = "quota_exceeded"
STATUS_RATE_LIMITED = "rate_limited"


def _spend_today(key_id: int) -> float:
    day_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    with get_session() as session:
        total = session.exec(
            select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0))
            .where(UsageRecord.key_id == key_id)
            .where(UsageRecord.timestamp >= day_start)
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


def _record_rejection(key_id: int, endpoint: str, model: str, reason: str) -> None:
    """Stamp a quota_exceeded / rate_limited row so the dashboard sees the rejection."""
    with get_session() as session:
        session.add(
            UsageRecord(
                key_id=key_id,
                model=model or "",
                endpoint=endpoint,
                status=reason,
                error=reason,
            )
        )
        session.commit()


def check_quotas(key: HubKey, endpoint: str = "", model: str = "") -> None:
    """Raise an HTTPException if the key has tripped its spend or rate quota.

    Spend is checked first; over-cap requests can't bypass it by being slow.
    """
    spent = _spend_today(key.id)
    if spent >= key.daily_spend_cap_usd:
        _record_rejection(key.id, endpoint, model, STATUS_QUOTA_EXCEEDED)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Daily spend cap of ${key.daily_spend_cap_usd:.2f} reached "
                f"(${spent:.4f} spent today). Resets at UTC midnight."
            ),
        )

    calls = _calls_in_last_minute(key.id)
    if calls >= key.rate_limit_per_min:
        _record_rejection(key.id, endpoint, model, STATUS_RATE_LIMITED)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit of {key.rate_limit_per_min} requests/minute exceeded "
                f"({calls} in the last 60 seconds)."
            ),
            headers={"Retry-After": "60"},
        )


async def enforce_quotas(key: HubKey = Depends(require_hub_key)) -> HubKey:
    """Dependency for /v1/* endpoints that should be quota-gated.

    Note: the model isn't known here (it's in the request body), so the
    rejection row gets ``model=""``. The endpoint-specific handler can
    re-check after parsing the body if you want per-model attribution —
    most callers don't need that.
    """
    check_quotas(key)
    return key

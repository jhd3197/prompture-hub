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

Reservations
------------
Usage rows are written when a call finishes, so :func:`reserve` also holds an
estimated cost (see :mod:`.reservations`) for each in-flight call. Spend,
reserved cost and in-flight calls are checked and the hold placed atomically,
so concurrent or streaming calls can't all pass on the same headroom.
:func:`enforce_quotas` stays the cheap early check on the same figures.

Refusals raise :class:`QuotaError`: the usual ``detail`` string plus a
machine-readable ``error`` object (see ``main.py`` for the rendering).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from prompture.companion import window_end, window_start
from sqlalchemy import func
from sqlmodel import select

from . import reservations
from .auth import require_hub_key
from .pricing import model_rates
from .reservations import Reservation
from .settings import get_settings
from .storage.db import get_session
from .storage.models import HubKey, SpendAdjustment, UsageRecord, iso_utc

logger = logging.getLogger("prompture_hub.quotas")

# Errors recorded for over-quota requests use these status strings so the
# admin dashboard can distinguish them from real provider errors.
STATUS_QUOTA_EXCEEDED = "quota_exceeded"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_PRICING_UNKNOWN = "pricing_unknown"


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
    """Effective spend in the cap window: usage cost plus manual adjustments made in it.

    Not clamped: a grant larger than current spend yields negative spend (extra headroom).
    """
    window_start = _window_start(period)
    with get_session() as session:
        used = session.exec(
            select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0))
            .where(UsageRecord.key_id == key_id)
            .where(UsageRecord.timestamp >= window_start)
        ).one()
        adjusted = session.exec(
            select(func.coalesce(func.sum(SpendAdjustment.amount_usd), 0.0))
            .where(SpendAdjustment.key_id == key_id)
            .where(SpendAdjustment.created_at >= window_start)
        ).one()
    return float(used or 0.0) + float(adjusted or 0.0)


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


class QuotaError(HTTPException):
    """A 402/429 refusal carrying a machine-readable ``error`` object next to ``detail``."""

    def __init__(self, status_code: int, detail: str, error: dict[str, Any], headers: dict[str, str] | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error = {"message": detail, **error}


def window_resets_at(period: str, now: datetime | None = None) -> datetime:
    """Next UTC boundary of the cap window: next midnight, next Monday or the 1st of next month."""
    return window_end(period, now)


def _violation(key: HubKey, estimate: float) -> QuotaError | None:
    """Why *key* may not start a call costing about *estimate*; ``None`` if it may.

    Counts reserved cost and in-flight calls, so callers hold ``reservations.lock``.
    """
    period = (getattr(key, "spend_period", "day") or "day").lower()
    cap = key.spend_cap_usd
    spent = _spend_in_window(key.id, period)
    reserved = reservations.reserved_usd(key.id)
    figures = {
        "type": "insufficient_quota",
        "period": period,
        "cap_usd": cap,
        "spent_usd": round(spent, 6),
        "reserved_usd": round(reserved, 6),
        "estimated_usd": round(estimate, 6),
        "window_start": iso_utc(_window_start(period)),
        "window_resets_at": iso_utc(window_resets_at(period)),
    }
    held = f", ${reserved:.4f} reserved by in-flight calls" if reserved else ""
    if spent + reserved >= cap:
        return QuotaError(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Spend cap of ${cap:.2f} per {period} reached (${spent:.4f} spent so far{held}). "
            f"Refusing calls for {_period_label(period)}.",
            {"code": "spend_cap_exceeded", **figures},
        )
    if spent + reserved + estimate > cap:
        return QuotaError(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"Spend cap of ${cap:.2f} per {period} would be exceeded: ${spent:.4f} spent so far{held}, "
            f"and this call is estimated at ${estimate:.4f}. Refusing until {_period_label(period)} "
            "resets, or retry with a smaller max_tokens.",
            {"code": "spend_cap_would_exceed", **figures},
        )
    calls = _calls_in_last_minute(key.id) + reservations.in_flight(key.id)
    if calls >= key.rate_limit_per_min:
        return QuotaError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Rate limit of {key.rate_limit_per_min} requests/minute exceeded "
            f"({calls} in the last 60 seconds, counting calls still in flight).",
            {
                "code": "rate_limit_exceeded",
                "type": "rate_limit_error",
                "limit_per_min": key.rate_limit_per_min,
                "in_last_minute": calls,
                "retry_after_seconds": 60,
            },
            headers={"Retry-After": "60"},
        )
    return None


def _refuse(err: QuotaError, key: HubKey, endpoint: str, model: str, project: str | None) -> None:
    reason = STATUS_RATE_LIMITED if err.status_code == status.HTTP_429_TOO_MANY_REQUESTS else STATUS_QUOTA_EXCEEDED
    _record_rejection(key.id, endpoint, model, reason, project)
    raise err


def check_quotas(key: HubKey, endpoint: str = "", model: str = "", project: str | None = None) -> None:
    """Raise a :class:`QuotaError` if the key has tripped its spend or rate quota.

    Spend is checked first; over-cap requests can't bypass it by being slow.
    """
    with reservations.lock:
        err = _violation(key, 0.0)
    if err:
        _refuse(err, key, endpoint, model, project)


def reserve(
    key: HubKey,
    model: str,
    endpoint: str,
    estimated_cost: float,
    project: str | None = None,
    **fields: Any,
) -> Reservation:
    """Atomically check the quotas against *estimated_cost* and hold it until the call settles.

    Refuses with 402 when the cap is reached or this call would push past it
    (counting what in-flight calls already hold), and with 429 when the
    per-minute limit is reached counting in-flight calls. Release the returned
    reservation when the call ends (``metering.record`` / ``Call.close`` do).
    """
    with reservations.lock:
        err = _violation(key, estimated_cost)
        if err is None:
            return reservations.add(
                key.id, estimated_cost, get_settings().reservation_ttl_seconds, **fields
            )
    _refuse(err, key, endpoint, model, project)


def admit(
    key: HubKey,
    model: str,
    endpoint: str,
    project: str | None,
    *,
    served_by: str | None = None,
    input_tokens: int,
    output_tokens: int | None = None,
) -> Reservation:
    """Price a call, then :func:`reserve` its estimated cost.

    *model* is what the caller asked for (rejections are recorded under it),
    *served_by* the model actually called (defaults to *model*). Tokens in
    the output default to ``HUB_DEFAULT_OUTPUT_TOKEN_ESTIMATE``.
    """
    settings = get_settings()
    rates = model_rates(served_by or model)
    if rates is None:
        if settings.unknown_pricing == "block":
            _record_rejection(key.id, endpoint, model, STATUS_PRICING_UNKNOWN, project)
            raise QuotaError(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"Pricing for model '{served_by or model}' is unknown, so its spend can't be metered "
                "against this key's cap. Set HUB_UNKNOWN_PRICING=warn to allow unpriced models, "
                "or give the key a model whitelist of priced models.",
                {
                    "code": "pricing_unknown",
                    "type": "invalid_request_error",
                    "model": served_by or model,
                    "setting": "HUB_UNKNOWN_PRICING",
                },
            )
        logger.warning("Unknown pricing for %s: allowing the call without a cost reservation", served_by or model)
        return reserve(key, model, endpoint, 0.0, project, unknown_pricing=True)
    if output_tokens is None:
        output_tokens = settings.default_output_token_estimate
    return reserve(
        key, model, endpoint, rates.cost(input_tokens, output_tokens), project,
        rates=rates, priced=not rates.free,
    )


async def enforce_quotas(request: Request, key: HubKey = Depends(require_hub_key)) -> HubKey:
    """Dependency for /v1/* endpoints that should be quota-gated.

    The cheap early check: cap reached or rate limit hit. Endpoints that know
    the model then call :func:`admit` to reserve the call's estimated cost.
    The model isn't known here (it's in the request body), so the
    rejection row gets ``model=""``.
    """
    from .metering import resolve_project

    check_quotas(key, endpoint=request.url.path, project=resolve_project(request, key))
    return key

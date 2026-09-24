"""Usage analytics for the dashboard: ``GET /api/analytics?days=N``.

Aggregates :class:`UsageRecord` rows in Python rather than SQL so the same
code runs on SQLite today and Postgres later without dialect-specific
percentile functions. At solo/team scale (≤ a few hundred thousand rows in
a 90-day window) this is well under a second.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import select

from ..auth import require_user
from ..storage.db import get_session
from ..storage.models import HubKey, UsageRecord, User, iso_utc
from .spa_api import _user_key_ids

router = APIRouter()

_ERROR_STATUSES = {"error"}
_BLOCKED_STATUSES = {"quota_exceeded", "rate_limited"}


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return int(ordered[idx])


class _Bucket:
    __slots__ = ("requests", "errors", "blocked", "cost", "tokens", "latencies", "fallbacks")

    def __init__(self) -> None:
        self.requests = 0
        self.errors = 0
        self.blocked = 0
        self.cost = 0.0
        self.tokens = 0
        self.latencies: list[int] = []
        self.fallbacks = 0

    def add(self, u: UsageRecord) -> None:
        self.requests += 1
        if u.status in _ERROR_STATUSES:
            self.errors += 1
        elif u.status in _BLOCKED_STATUSES:
            self.blocked += 1
        self.cost += u.cost_usd or 0.0
        self.tokens += u.total_tokens or 0
        if u.status == "ok" and u.latency_ms:
            self.latencies.append(u.latency_ms)
        # A combo is always served by one of its members, so a different
        # served_by alone isn't a fallback — needing a second attempt is.
        if (u.attempts or 1) > 1:
            self.fallbacks += 1

    def to_dict(self) -> dict[str, Any]:
        served = self.requests - self.blocked
        return {
            "requests": self.requests,
            "errors": self.errors,
            "blocked": self.blocked,
            "error_rate": round(self.errors / served, 4) if served else 0.0,
            "cost_usd": round(self.cost, 6),
            "tokens": self.tokens,
            "p50_latency_ms": _percentile(self.latencies, 50),
            "p95_latency_ms": _percentile(self.latencies, 95),
            "fallbacks": self.fallbacks,
            "fallback_rate": round(self.fallbacks / served, 4) if served else 0.0,
        }


@router.get("/analytics")
def analytics(
    days: int = Query(default=7, ge=1, le=90),
    user: User = Depends(require_user),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    key_ids = _user_key_ids(user)

    with get_session() as session:
        stmt = select(UsageRecord).where(UsageRecord.timestamp >= start)
        if key_ids is not None:
            stmt = stmt.where(UsageRecord.key_id.in_(key_ids or [-1]))
        rows = session.exec(stmt).all()
        key_names = {k.id: k.name for k in session.exec(select(HubKey)).all()}

    totals = _Bucket()
    by_day: dict[str, _Bucket] = defaultdict(_Bucket)
    by_model: dict[str, _Bucket] = defaultdict(_Bucket)
    by_provider: dict[str, _Bucket] = defaultdict(_Bucket)
    by_key: dict[int, _Bucket] = defaultdict(_Bucket)
    errors: list[UsageRecord] = []

    for u in rows:
        ts = u.timestamp if u.timestamp.tzinfo else u.timestamp.replace(tzinfo=timezone.utc)
        totals.add(u)
        by_day[ts.date().isoformat()].add(u)
        if u.model:
            by_model[u.model].add(u)
        served = u.served_by or u.model
        if served:
            by_provider[served.split("/", 1)[0]].add(u)
        by_key[u.key_id].add(u)
        if u.status in _ERROR_STATUSES:
            errors.append(u)

    day_list = []
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        day_list.append({"date": d, **(by_day[d].to_dict() if d in by_day else _Bucket().to_dict())})

    def ranked(buckets: dict[Any, _Bucket], label: str) -> list[dict[str, Any]]:
        items = [{label: k, **b.to_dict()} for k, b in buckets.items()]
        return sorted(items, key=lambda r: (-r["cost_usd"], -r["requests"]))

    by_key_list = ranked(by_key, "key_id")
    for row in by_key_list:
        row["name"] = key_names.get(row["key_id"], f"key {row['key_id']}")

    errors.sort(key=lambda u: u.timestamp, reverse=True)
    return {
        "range": {"start": iso_utc(start), "end": iso_utc(now), "days": days},
        "totals": totals.to_dict(),
        "by_day": day_list,
        "by_model": ranked(by_model, "model"),
        "by_provider": ranked(by_provider, "provider"),
        "by_key": by_key_list,
        "recent_errors": [
            {
                "timestamp": iso_utc(u.timestamp),
                "model": u.model,
                "served_by": u.served_by,
                "key_id": u.key_id,
                "key_name": key_names.get(u.key_id),
                "endpoint": u.endpoint,
                "error": (u.error or "")[:300],
            }
            for u in errors[:20]
        ],
    }

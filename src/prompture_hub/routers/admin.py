"""Admin endpoints: create/list/revoke hub keys, browse usage records.

All routes gated by ``require_admin`` (bearer ``HUB_ADMIN_TOKEN``). This credential
is intentionally separate from hub-issued user keys — separation of duties.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from .. import audit, live
from ..auth import generate_key, require_admin
from ..metering import clean_project
from ..policies import is_expired, normalize_ip_rules, resolve_expiry
from ..quotas import _window_start, spend_in_window
from ..storage.db import get_session
from ..storage.models import AuditLog, HubKey, SpendAdjustment, UsageRecord, User, iso_utc

router = APIRouter(dependencies=[Depends(require_admin)])


class CreateKeyRequest(BaseModel):
    name: str
    allowed_models: list[str] = Field(default_factory=list)
    daily_spend_cap_usd: float = 1.0
    spend_period: str = Field(
        default="day",
        description="day | week | month — UTC window the spend cap resets on.",
    )
    rate_limit_per_min: int = 60
    allowed_ips: list[str] = Field(default_factory=list, description="IPs / CIDR ranges; empty = any.")
    expires_at: datetime | None = None
    expires_in_days: int | None = Field(default=None, description="Alternative to expires_at.")
    user_email: str | None = Field(
        default=None,
        description="Optional. If set, the key is attached to that user (must already exist).",
    )
    default_project: str | None = Field(
        default=None, max_length=100, description="Project for calls that send no X-Project header."
    )


class CreateKeyResponse(BaseModel):
    id: int
    name: str
    key: str = Field(description="Plaintext key — shown ONCE. Save it now.")
    allowed_models: list[str]
    daily_spend_cap_usd: float
    spend_period: str
    rate_limit_per_min: int
    allowed_ips: list[str] = Field(default_factory=list)
    expires_at: str | None = None
    user_id: int | None = None
    user_email: str | None = None
    default_project: str | None = None


@router.post("/keys", response_model=CreateKeyResponse, status_code=status.HTTP_201_CREATED)
def create_key(body: CreateKeyRequest) -> CreateKeyResponse:
    plaintext, hashed = generate_key()
    with get_session() as session:
        user_id: int | None = None
        user_email: str | None = None
        if body.user_email:
            normalized = body.user_email.strip().lower()
            user_row = session.exec(
                select(User).where(User.email == normalized)
            ).first()
            if not user_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No user with email '{normalized}'. They must log in once first.",
                )
            user_id = user_row.id
            user_email = user_row.email

        period = (body.spend_period or "day").lower()
        if period not in {"day", "week", "month"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"spend_period must be day|week|month, got {body.spend_period!r}",
            )

        row = HubKey(
            name=body.name,
            hashed_secret=hashed,
            allowed_models=body.allowed_models,
            daily_spend_cap_usd=body.daily_spend_cap_usd,
            spend_period=period,
            rate_limit_per_min=body.rate_limit_per_min,
            allowed_ips=normalize_ip_rules(body.allowed_ips),
            expires_at=resolve_expiry(body.expires_at, body.expires_in_days),
            user_id=user_id,
            default_project=clean_project(body.default_project),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return CreateKeyResponse(
            id=row.id,
            name=row.name,
            key=plaintext,
            allowed_models=row.allowed_models,
            daily_spend_cap_usd=row.daily_spend_cap_usd,
            spend_period=row.spend_period,
            rate_limit_per_min=row.rate_limit_per_min,
            allowed_ips=row.allowed_ips or [],
            expires_at=iso_utc(row.expires_at),
            user_id=user_id,
            user_email=user_email,
            default_project=row.default_project,
        )


def _key_dict(r: HubKey) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "allowed_models": r.allowed_models,
        "daily_spend_cap_usd": r.daily_spend_cap_usd,
        "spend_period": r.spend_period,
        "rate_limit_per_min": r.rate_limit_per_min,
        "created_at": iso_utc(r.created_at),
        "revoked_at": iso_utc(r.revoked_at),
        "allowed_ips": r.allowed_ips or [],
        "expires_at": iso_utc(r.expires_at),
        "expired": is_expired(r),
        "active": r.revoked_at is None and not is_expired(r),
        "user_id": r.user_id,
        "default_project": r.default_project,
        "paused": r.paused_at is not None,
        "route_override": r.route_override,
        "spent_in_window": round(spend_in_window(r.id, r.spend_period or "day"), 6),
    }


@router.get("/keys")
def list_keys() -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.exec(select(HubKey).order_by(HubKey.created_at.desc())).all()
        return [_key_dict(r) for r in rows]


class AdminKeyPatch(BaseModel):
    daily_spend_cap_usd: float | None = Field(default=None, ge=0)
    spend_period: str | None = Field(default=None, pattern="^(day|week|month)$")
    rate_limit_per_min: int | None = Field(default=None, ge=1)


class SpendReason(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class GrantRequest(SpendReason):
    amount_usd: float = Field(gt=0)


def _active_key(session: Any, key_id: int) -> HubKey:
    row = session.get(HubKey, key_id)
    if not row or row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")
    return row


@router.patch("/keys/{key_id}")
def update_key(key_id: int, body: AdminKeyPatch) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(v is None for v in changes.values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Send at least one of daily_spend_cap_usd, spend_period, rate_limit_per_min (none can be null).",
        )
    with get_session() as session:
        row = _active_key(session, key_id)
        before = {name: getattr(row, name) for name in changes if getattr(row, name) != changes[name]}
        for name, value in changes.items():
            setattr(row, name, value)
        session.add(row)
        session.commit()
        session.refresh(row)
        result = _key_dict(row)
        name = row.name
    if before:
        audit.record(
            audit.ADMIN_ACTOR, "key.update", key_id, {"before": before, "after": {n: changes[n] for n in before}}
        )
    live.get_bus().publish(
        "key.updated", {"key_id": key_id, "key_name": name, "changes": changes, "by": "admin"}
    )
    return result


def _adjust_spend(key_id: int, kind: str, reason: str | None, amount: float | None) -> dict[str, Any]:
    """Insert a SpendAdjustment (``amount`` None = bring the window to exactly zero) and audit it."""
    with get_session() as session:
        row = _active_key(session, key_id)
        period = row.spend_period or "day"
        cap = row.daily_spend_cap_usd
    before = spend_in_window(key_id, period)
    delta = -before if amount is None else -amount
    with get_session() as session:
        session.add(
            SpendAdjustment(
                key_id=key_id, amount_usd=delta, kind=kind, reason=reason, actor_label=audit.ADMIN_LABEL
            )
        )
        session.commit()
    after = spend_in_window(key_id, period)
    details: dict[str, Any] = {
        "spent_before": round(before, 6),
        "spent_after": round(after, 6),
        "window": iso_utc(_window_start(period)),
        "period": period,
        "reason": reason,
    }
    if kind == "grant":
        details["amount_usd"] = amount
    audit.record(audit.ADMIN_ACTOR, f"key.spend_{kind}", key_id, details)
    return {
        "key_id": key_id,
        "period": period,
        "spent_before": round(before, 6),
        "spent_after": round(after, 6),
        "cap": cap,
    }


@router.post("/keys/{key_id}/reset-spend")
def reset_spend(key_id: int, body: SpendReason | None = None) -> dict[str, Any]:
    return _adjust_spend(key_id, "reset", body.reason if body else None, None)


@router.post("/keys/{key_id}/grant")
def grant_spend(key_id: int, body: GrantRequest) -> dict[str, Any]:
    return _adjust_spend(key_id, "grant", body.reason, body.amount_usd)


@router.get("/keys/{key_id}/adjustments")
def list_adjustments(key_id: int) -> list[dict[str, Any]]:
    """Adjustments that count toward the key's current window."""
    with get_session() as session:
        row = session.get(HubKey, key_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")
        stmt = (
            select(SpendAdjustment)
            .where(SpendAdjustment.key_id == key_id)
            .where(SpendAdjustment.created_at >= _window_start(row.spend_period or "day"))
            .order_by(SpendAdjustment.created_at.desc(), SpendAdjustment.id.desc())
        )
        return [
            {
                "id": a.id,
                "amount_usd": a.amount_usd,
                "kind": a.kind,
                "reason": a.reason,
                "actor_label": a.actor_label,
                "created_at": iso_utc(a.created_at),
            }
            for a in session.exec(stmt).all()
        ]


@router.get("/audit")
def list_audit(
    key_id: int | None = None, action: str | None = None, limit: int = Query(default=100, ge=1, le=500)
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
        if key_id is not None:
            stmt = stmt.where(AuditLog.key_id == key_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return [
            {
                "id": a.id,
                "created_at": iso_utc(a.created_at),
                "actor_kind": a.actor_kind,
                "actor_id": a.actor_id,
                "actor_label": a.actor_label,
                "action": a.action,
                "key_id": a.key_id,
                "details": a.details,
            }
            for a in session.exec(stmt).all()
        ]


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(key_id: int) -> Response:
    with get_session() as session:
        row = session.get(HubKey, key_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")
        row.revoked_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/usage")
def list_usage(
    key_id: int | None = None,
    model: str | None = None,
    project: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(UsageRecord).order_by(UsageRecord.timestamp.desc()).limit(limit)
        if key_id is not None:
            stmt = stmt.where(UsageRecord.key_id == key_id)
        if model:
            stmt = stmt.where(UsageRecord.model == model)
        if project:
            stmt = stmt.where(UsageRecord.project == project)
        return [
            {
                "id": r.id,
                "key_id": r.key_id,
                "model": r.model,
                "endpoint": r.endpoint,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "status": r.status,
                "project": r.project,
                "timestamp": iso_utc(r.timestamp),
            }
            for r in session.exec(stmt).all()
        ]

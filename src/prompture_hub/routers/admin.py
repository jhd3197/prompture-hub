"""Admin endpoints: create/list/revoke hub keys, browse usage records.

All routes gated by ``require_admin`` (bearer ``HUB_ADMIN_TOKEN``). This credential
is intentionally separate from hub-issued user keys — separation of duties.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from ..auth import generate_key, require_admin
from ..policies import is_expired, normalize_ip_rules, resolve_expiry
from ..storage.db import get_session
from ..storage.models import HubKey, UsageRecord, User, iso_utc

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
        )


@router.get("/keys")
def list_keys() -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.exec(select(HubKey).order_by(HubKey.created_at.desc())).all()
        return [
            {
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
            }
            for r in rows
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
    limit: int = 100,
) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(UsageRecord).order_by(UsageRecord.timestamp.desc()).limit(limit)
        if key_id is not None:
            stmt = stmt.where(UsageRecord.key_id == key_id)
        if model:
            stmt = stmt.where(UsageRecord.model == model)
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
                "timestamp": iso_utc(r.timestamp),
            }
            for r in session.exec(stmt).all()
        ]

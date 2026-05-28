"""JSON endpoints consumed by the React SPA.

Separate from the older Jinja-driven dashboard routes so the SPA contract
is explicit and stable. All endpoints under ``/api/*`` return JSON and
expect the same session cookie the dashboard uses.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select

from ..auth import generate_key, require_user
from ..settings import get_settings
from ..storage.db import get_session
from ..storage.models import Conversation, HubKey, Message, UsageRecord, User

router = APIRouter()


def _user_scope(user: User) -> bool:
    return get_settings().auth_enabled and user.id is not None and user.id > 0


def _serialize_key(k: HubKey) -> dict[str, Any]:
    return {
        "id": k.id,
        "name": k.name,
        "allowed_models": k.allowed_models,
        "daily_spend_cap_usd": k.daily_spend_cap_usd,
        "rate_limit_per_min": k.rate_limit_per_min,
        "created_at": k.created_at.isoformat(),
        "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
        "active": k.revoked_at is None,
    }


def _serialize_usage(u: UsageRecord) -> dict[str, Any]:
    return {
        "id": u.id,
        "key_id": u.key_id,
        "model": u.model,
        "endpoint": u.endpoint,
        "prompt_tokens": u.prompt_tokens,
        "completion_tokens": u.completion_tokens,
        "total_tokens": u.total_tokens,
        "cost_usd": u.cost_usd,
        "latency_ms": u.latency_ms,
        "status": u.status,
        "timestamp": u.timestamp.isoformat(),
    }


@router.get("/me")
def me(user: User = Depends(require_user)) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "provider": user.provider,
    }


@router.get("/auth/providers")
def auth_providers() -> dict[str, Any]:
    s = get_settings()
    return {
        "google": s.google_enabled,
        "github": s.github_enabled,
        "auth_configured": s.auth_enabled,
    }


@router.get("/overview")
def overview(user: User = Depends(require_user)) -> dict[str, Any]:
    scoped = _user_scope(user)
    with get_session() as session:
        keys_stmt = (
            select(HubKey)
            .order_by(HubKey.created_at.desc())
            .limit(10)
        )
        if scoped:
            keys_stmt = keys_stmt.where(HubKey.user_id == user.id)
        recent_keys = session.exec(keys_stmt).all()

        if scoped:
            user_key_ids = [
                k.id for k in session.exec(
                    select(HubKey.id).where(HubKey.user_id == user.id)
                ).all()
            ]
        else:
            user_key_ids = None

        usage_stmt = (
            select(UsageRecord)
            .order_by(UsageRecord.timestamp.desc())
            .limit(20)
        )
        if user_key_ids is not None:
            usage_stmt = usage_stmt.where(UsageRecord.key_id.in_(user_key_ids or [-1]))
        recent_usage = session.exec(usage_stmt).all()

        day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        spend_stmt = select(
            func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)
        ).where(UsageRecord.timestamp >= day_ago)
        if user_key_ids is not None:
            spend_stmt = spend_stmt.where(UsageRecord.key_id.in_(user_key_ids or [-1]))
        spend_24h = float(session.exec(spend_stmt).one() or 0.0)

        active_stmt = select(func.count(HubKey.id)).where(HubKey.revoked_at.is_(None))
        if scoped:
            active_stmt = active_stmt.where(HubKey.user_id == user.id)
        active_count = int(session.exec(active_stmt).one() or 0)

    return {
        "spend_24h": spend_24h,
        "active_key_count": active_count,
        "total_call_count": len(recent_usage),
        "recent_usage": [_serialize_usage(u) for u in recent_usage],
        "recent_keys": [_serialize_key(k) for k in recent_keys],
    }


@router.get("/keys")
def list_keys(user: User = Depends(require_user)) -> list[dict[str, Any]]:
    scoped = _user_scope(user)
    with get_session() as session:
        stmt = select(HubKey).order_by(HubKey.created_at.desc())
        if scoped:
            stmt = stmt.where(HubKey.user_id == user.id)
        return [_serialize_key(k) for k in session.exec(stmt).all()]


class CreateKeyBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    allowed_models: list[str] = Field(default_factory=list)
    daily_spend_cap_usd: float = Field(default=1.0, ge=0)
    rate_limit_per_min: int = Field(default=60, ge=1)


@router.post("/keys", status_code=status.HTTP_201_CREATED)
def create_key(
    body: CreateKeyBody,
    user: User = Depends(require_user),
) -> dict[str, Any]:
    plaintext, hashed = generate_key()
    user_id = user.id if (user.id and user.id > 0) else None
    with get_session() as session:
        row = HubKey(
            name=body.name.strip(),
            hashed_secret=hashed,
            allowed_models=[m.strip() for m in body.allowed_models if m.strip()],
            daily_spend_cap_usd=body.daily_spend_cap_usd,
            rate_limit_per_min=body.rate_limit_per_min,
            user_id=user_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {
            "id": row.id,
            "name": row.name,
            "key": plaintext,
            "allowed_models": row.allowed_models,
            "daily_spend_cap_usd": row.daily_spend_cap_usd,
            "rate_limit_per_min": row.rate_limit_per_min,
        }


@router.post("/keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(key_id: int, user: User = Depends(require_user)) -> None:
    scoped = _user_scope(user)
    with get_session() as session:
        row = session.get(HubKey, key_id)
        if not row or (scoped and row.user_id != user.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Key not found.",
            )
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()


# ---------------------------------------------------------------------------
# Conversations — user-scoped, joined through HubKey.user_id.
# ---------------------------------------------------------------------------


def _user_key_ids(user: User) -> list[int] | None:
    """Return the IDs of every HubKey owned by ``user``, or ``None`` when
    user-scoping is disabled (localhost-open dev mode)."""
    if not _user_scope(user):
        return None
    with get_session() as session:
        return [
            k.id for k in session.exec(
                select(HubKey.id).where(HubKey.user_id == user.id)
            ).all()
        ]


def _require_owned_conversation(conv_id: str, user: User) -> Conversation:
    with get_session() as session:
        conv = session.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    user_keys = _user_key_ids(user)
    if user_keys is not None and conv.key_id not in user_keys:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    return conv


@router.get("/conversations")
def list_conversations(
    limit: int = 50,
    user: User = Depends(require_user),
) -> list[dict[str, Any]]:
    user_keys = _user_key_ids(user)
    with get_session() as session:
        stmt = (
            select(Conversation)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        if user_keys is not None:
            stmt = stmt.where(Conversation.key_id.in_(user_keys or [-1]))
        convs = session.exec(stmt).all()

        out: list[dict[str, Any]] = []
        for c in convs:
            msg_count = len(
                session.exec(
                    select(Message.id).where(Message.conversation_id == c.id)
                ).all()
            )
            out.append({
                "id": c.id,
                "title": c.title,
                "model": c.model,
                "key_id": c.key_id,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat(),
                "message_count": msg_count,
            })
        return out


@router.get("/conversations/{conv_id}")
def get_conversation(
    conv_id: str,
    user: User = Depends(require_user),
) -> dict[str, Any]:
    conv = _require_owned_conversation(conv_id, user)
    with get_session() as session:
        msgs = session.exec(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
        ).all()

    total_prompt = sum(m.prompt_tokens for m in msgs)
    total_completion = sum(m.completion_tokens for m in msgs)
    total_cost = sum(m.cost_usd for m in msgs)

    return {
        "id": conv.id,
        "title": conv.title,
        "model": conv.model,
        "key_id": conv.key_id,
        "meta": conv.meta or {},
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "totals": {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "cost_usd": total_cost,
            "message_count": len(msgs),
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "total_tokens": m.total_tokens,
                "cost_usd": m.cost_usd,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }


@router.delete(
    "/conversations/{conv_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conv_id: str,
    user: User = Depends(require_user),
) -> None:
    _require_owned_conversation(conv_id, user)
    with get_session() as session:
        for m in session.exec(
            select(Message).where(Message.conversation_id == conv_id)
        ).all():
            session.delete(m)
        conv = session.get(Conversation, conv_id)
        if conv:
            session.delete(conv)
        session.commit()


# ---------------------------------------------------------------------------


@router.get("/models")
def models() -> dict[str, Any]:
    discovery_error: str | None = None
    names: list[str] = []
    try:
        from prompture.infra.discovery import get_available_models
        names = list(get_available_models())
    except Exception as exc:  # noqa: BLE001
        discovery_error = str(exc)

    by_provider: dict[str, list[str]] = {}
    for n in names:
        if "/" in n:
            provider, model = n.split("/", 1)
        else:
            provider, model = "unknown", n
        by_provider.setdefault(provider, []).append(model)
    for ms in by_provider.values():
        ms.sort()

    groups = [
        {"provider": provider, "models": ms}
        for provider, ms in sorted(by_provider.items())
    ]
    return {
        "groups": groups,
        "total": len(names),
        "discovery_error": discovery_error,
    }

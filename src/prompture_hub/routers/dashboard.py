"""Server-rendered dashboard (v0.1).

Jinja2 templates + Tailwind via CDN — no Node toolchain. Intentionally simple so the
backend API contract can stabilize before we invest in a proper React frontend
(planned for v0.2, matching CachiBot's Vite/TS/Tailwind stack).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlmodel import select

from ..auth import generate_key, require_user
from ..settings import get_settings
from ..storage.db import get_session
from ..storage.models import HubKey, User, UsageRecord


def _user_filter_enabled(user: User) -> bool:
    """True when we should restrict queries to ``HubKey.user_id == user.id``.

    Skipped in the fallback localhost-open mode (auth not configured) so
    solo dev still sees every row.
    """
    return get_settings().auth_enabled and user.id is not None and user.id > 0

router = APIRouter()
_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@router.get("/", response_class=HTMLResponse)
def home(request: Request, current_user: User = Depends(require_user)) -> HTMLResponse:
    scoped = _user_filter_enabled(current_user)
    with get_session() as session:
        keys_stmt = select(HubKey).order_by(HubKey.created_at.desc()).limit(10)
        if scoped:
            keys_stmt = keys_stmt.where(HubKey.user_id == current_user.id)
        keys = session.exec(keys_stmt).all()

        usage_stmt = select(UsageRecord).order_by(UsageRecord.timestamp.desc()).limit(10)
        if scoped:
            user_key_ids = [
                k.id
                for k in session.exec(
                    select(HubKey.id).where(HubKey.user_id == current_user.id)
                ).all()
            ]
            usage_stmt = usage_stmt.where(UsageRecord.key_id.in_(user_key_ids or [-1]))
        recent_usage = session.exec(usage_stmt).all()

        day_ago = datetime.now(timezone.utc) - timedelta(days=1)
        spend_stmt = select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)).where(
            UsageRecord.timestamp >= day_ago
        )
        if scoped:
            spend_stmt = spend_stmt.where(UsageRecord.key_id.in_(user_key_ids or [-1]))
        spend_24h = session.exec(spend_stmt).one()

        active_stmt = select(func.count(HubKey.id)).where(HubKey.revoked_at.is_(None))
        if scoped:
            active_stmt = active_stmt.where(HubKey.user_id == current_user.id)
        active_key_count = session.exec(active_stmt).one()

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "keys": keys,
            "recent_usage": recent_usage,
            "spend_24h": float(spend_24h or 0.0),
            "active_key_count": int(active_key_count or 0),
            "current_user": current_user,
        },
    )


@router.get("/keys", response_class=HTMLResponse)
def keys_page(request: Request, current_user: User = Depends(require_user)) -> HTMLResponse:
    scoped = _user_filter_enabled(current_user)
    with get_session() as session:
        stmt = select(HubKey).order_by(HubKey.created_at.desc())
        if scoped:
            stmt = stmt.where(HubKey.user_id == current_user.id)
        keys = session.exec(stmt).all()

    new_key: dict | None = None
    if hasattr(request, "session"):
        new_key = request.session.pop("last_created_key", None)

    return templates.TemplateResponse(
        request,
        "keys.html",
        {
            "keys": keys,
            "current_user": current_user,
            "new_key": new_key,
            "form_error": request.query_params.get("error"),
        },
    )


@router.post("/keys")
def create_key_form(
    request: Request,
    name: str = Form(..., min_length=1, max_length=100),
    allowed_models: str = Form(default=""),
    daily_spend_cap_usd: float = Form(default=1.0),
    rate_limit_per_min: int = Form(default=60),
    current_user: User = Depends(require_user),
) -> RedirectResponse:
    """Self-serve key creation. Auto-attaches the new key to ``current_user``."""
    if daily_spend_cap_usd < 0:
        return RedirectResponse(url="/keys?error=negative_spend_cap", status_code=303)
    if rate_limit_per_min < 1:
        return RedirectResponse(url="/keys?error=invalid_rate_limit", status_code=303)

    models = [m.strip() for m in allowed_models.split(",") if m.strip()]
    plaintext, hashed = generate_key()

    user_id = current_user.id if (current_user.id and current_user.id > 0) else None

    with get_session() as session:
        row = HubKey(
            name=name.strip(),
            hashed_secret=hashed,
            allowed_models=models,
            daily_spend_cap_usd=daily_spend_cap_usd,
            rate_limit_per_min=rate_limit_per_min,
            user_id=user_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        row_id = row.id
        row_name = row.name

    if hasattr(request, "session"):
        request.session["last_created_key"] = {
            "id": row_id,
            "name": row_name,
            "plaintext": plaintext,
        }
    return RedirectResponse(url="/keys", status_code=303)


@router.post("/keys/{key_id}/revoke")
def revoke_key_form(
    key_id: int,
    current_user: User = Depends(require_user),
) -> RedirectResponse:
    """Revoke one of the caller's own keys. Anyone else's → 404."""
    scoped = _user_filter_enabled(current_user)
    with get_session() as session:
        row = session.get(HubKey, key_id)
        if not row or (scoped and row.user_id != current_user.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Key not found.",
            )
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
    return RedirectResponse(url="/keys", status_code=303)


@router.get("/models", response_class=HTMLResponse)
def models_page(request: Request, current_user: User = Depends(require_user)) -> HTMLResponse:
    discovery_error: str | None = None
    names: list[str] = []
    try:
        from prompture.infra.discovery import get_available_models
        names = list(get_available_models())
    except Exception as exc:
        discovery_error = str(exc)

    by_provider: dict[str, list[str]] = {}
    for n in names:
        if "/" in n:
            provider, model = n.split("/", 1)
        else:
            provider, model = "unknown", n
        by_provider.setdefault(provider, []).append(model)
    for models in by_provider.values():
        models.sort()
    grouped = sorted(by_provider.items())

    return templates.TemplateResponse(
        request,
        "models.html",
        {
            "grouped_models": grouped,
            "total_count": len(names),
            "discovery_error": discovery_error,
            "current_user": current_user,
        },
    )

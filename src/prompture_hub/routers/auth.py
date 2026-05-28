"""Dashboard authentication via Google + GitHub OAuth.

Flow
----
1. ``GET /auth/login`` — renders login page with enabled providers.
2. ``GET /auth/{provider}/start`` — redirects to provider's authorize URL.
3. ``GET /auth/{provider}/callback`` — exchanges code, loads email, enforces
   the allowlist, upserts a User row, sets session cookie, redirects to ``/``.
4. ``POST /auth/logout`` — clears the session.

Allowlist
---------
``HUB_ALLOWED_EMAILS`` is comma-separated and case-insensitive. An empty
allowlist means no one can log in — a deliberate safe default so the
dashboard is never wide-open by accident.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import select

from ..oauth import get_oauth
from ..settings import get_settings
from ..storage.db import get_session
from ..storage.models import User

router = APIRouter()


@router.get("/login")
def login_page(request: Request) -> RedirectResponse:
    """The SPA renders the login UI. Any error param is preserved."""
    qs = request.url.query
    target = "/app/" + (f"?{qs}" if qs else "")
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@router.get("/{provider}/start")
async def oauth_start(provider: str, request: Request):
    s = get_settings()
    if not s.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard login is not configured (HUB_SESSION_SECRET + a provider required).",
        )
    oauth = get_oauth()
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider}' is not configured.",
        )
    redirect_uri = f"{s.base_url.rstrip('/')}/auth/{provider}/callback"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/{provider}/callback")
async def oauth_callback(provider: str, request: Request):
    s = get_settings()
    oauth = get_oauth()
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider}' is not configured.",
        )

    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(
            url=f"/app/?error=oauth_failed:{exc}",
            status_code=status.HTTP_302_FOUND,
        )

    email: str | None = None
    name: str | None = None
    avatar: str | None = None
    provider_user_id: str | None = None

    if provider == "google":
        info = token.get("userinfo") or {}
        if not info:
            info = await client.userinfo(token=token)
        email = (info.get("email") or "").lower() or None
        name = info.get("name")
        avatar = info.get("picture")
        provider_user_id = info.get("sub")
    elif provider == "github":
        user_resp = await client.get("user", token=token)
        u = user_resp.json()
        provider_user_id = str(u.get("id")) if u.get("id") is not None else None
        name = u.get("name") or u.get("login")
        avatar = u.get("avatar_url")
        email = (u.get("email") or "").lower() or None
        if not email:
            emails_resp = await client.get("user/emails", token=token)
            for e in emails_resp.json() or []:
                if e.get("primary") and e.get("verified"):
                    email = (e.get("email") or "").lower() or None
                    break

    if not email or not provider_user_id:
        return RedirectResponse(
            url="/app/?error=no_email_from_provider",
            status_code=status.HTTP_302_FOUND,
        )

    allowlist = s.allowed_email_set
    if not allowlist or email not in allowlist:
        return RedirectResponse(
            url="/app/?error=email_not_allowlisted",
            status_code=status.HTTP_302_FOUND,
        )

    with get_session() as session:
        existing = session.exec(select(User).where(User.email == email)).first()
        now = datetime.now(timezone.utc)
        if existing:
            existing.last_login_at = now
            existing.name = name or existing.name
            existing.avatar_url = avatar or existing.avatar_url
            existing.provider = provider
            existing.provider_user_id = provider_user_id
            session.add(existing)
            session.commit()
            user_id = existing.id
        else:
            row = User(
                email=email,
                name=name,
                avatar_url=avatar,
                provider=provider,
                provider_user_id=provider_user_id,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            user_id = row.id

    request.session["user_id"] = user_id
    request.session["email"] = email
    return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/app/", status_code=status.HTTP_302_FOUND)

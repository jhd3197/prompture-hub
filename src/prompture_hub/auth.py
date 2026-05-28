"""Auth dependencies for prompture-hub.

Two layers, intentionally separated:
- `require_admin` — protects /admin/* with bearer HUB_ADMIN_TOKEN
- `require_hub_key` — protects /v1/* with hub-issued scoped keys

Scoped keys are stored as SHA-256 hashes; the plaintext is shown once on
creation and never persisted.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import select

from .settings import HubSettings, get_settings
from .storage.db import get_session
from .storage.models import HubKey, User

KEY_PREFIX = "ph_"


def generate_key() -> tuple[str, str]:
    """Return ``(plaintext, sha256_hash)``. Plaintext is shown to caller exactly once."""
    raw = secrets.token_urlsafe(32)
    plaintext = f"{KEY_PREFIX}{raw}"
    hashed = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, hashed


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return authorization.strip() or None


async def require_admin(
    authorization: Annotated[str | None, Header()] = None,
    settings: HubSettings = Depends(get_settings),
) -> None:
    """Validate ``Authorization: Bearer <HUB_ADMIN_TOKEN>``."""
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HUB_ADMIN_TOKEN is not configured; /admin/* is disabled.",
        )
    provided = _extract_bearer(authorization)
    if not provided or not secrets.compare_digest(provided, settings.admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class LoginRequired(Exception):
    """Raised from require_user; main.py installs a handler that returns
    a RedirectResponse to ``/auth/login`` so browsers flow into OAuth."""

    def __init__(self, target: str = "/auth/login") -> None:
        self.target = target


def require_user(request: Request) -> User:
    """Gate a dashboard route. Returns the logged-in :class:`User` row.

    Browser requests get redirected to ``/auth/login`` (via :class:`LoginRequired`).
    JSON clients (Accept: application/json) get a 401.
    """
    settings = get_settings()
    if not settings.auth_enabled:
        # Auth not configured — fall back to open mode so localhost dev still works.
        return User(
            id=0,
            email="local@localhost",
            name="local",
            provider="none",
            provider_user_id="0",
        )

    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        accept = (request.headers.get("accept") or "").lower()
        if "application/json" in accept and "text/html" not in accept:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Login required.",
            )
        raise LoginRequired()

    with get_session() as session:
        user = session.get(User, user_id)
    if not user or user.email.lower() not in settings.allowed_email_set:
        if hasattr(request, "session"):
            request.session.clear()
        raise LoginRequired(target="/auth/login?error=email_not_allowlisted")
    return user


async def require_hub_key(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> HubKey:
    """Validate a hub-scoped key from ``Authorization: Bearer`` or ``X-API-Key``.

    Returns the loaded :class:`HubKey` row so downstream handlers can check
    ``allowed_models`` / quotas without a second lookup.
    """
    plaintext = _extract_bearer(authorization) or x_api_key
    if not plaintext:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing hub API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    hashed = hash_key(plaintext)
    with get_session() as session:
        statement = select(HubKey).where(
            HubKey.hashed_secret == hashed,
            HubKey.revoked_at.is_(None),
        )
        key = session.exec(statement).first()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked hub key.",
        )
    return key

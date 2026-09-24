"""Credentials for companion clients (desktop apps, status widgets).

A companion authenticates with one of:

- a **device token** (``phd_…``) minted through device pairing, carrying
  ``read`` and optionally ``control`` scope;
- the **admin token** (``HUB_ADMIN_TOKEN``), which has every scope;
- a **dashboard session**, which lets the web UI use the same endpoints.

Hub keys (``ph_…``) are deliberately not accepted: they belong to apps
that call models, not to people watching the hub.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Header, HTTPException, Request, status
from sqlmodel import select

from .settings import get_settings
from .storage.db import get_session
from .storage.models import DeviceToken

DEVICE_TOKEN_PREFIX = "phd_"
SCOPES = ("read", "control")

# Writing last_used_at on every request would turn each poll into a DB write.
_LAST_USED_RESOLUTION = timedelta(minutes=1)


@dataclass(frozen=True)
class Principal:
    """Who is calling a companion endpoint."""

    kind: str  # "device" | "admin" | "user"
    scopes: frozenset[str] = field(default_factory=frozenset)
    user_id: int | None = None
    device_id: int | None = None

    @property
    def sees_everything(self) -> bool:
        """Admin, or any caller while dashboard login is not configured (localhost-open mode)."""
        return self.kind == "admin" or not get_settings().auth_enabled or not self.user_id


def generate_device_token() -> tuple[str, str]:
    plaintext = DEVICE_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return plaintext, hash_secret(plaintext)


def hash_secret(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


def normalize_scopes(raw: list[str] | str | None) -> list[str]:
    """``read`` is always included; ``control`` only when asked for."""
    items = raw.split() if isinstance(raw, str) else list(raw or [])
    wanted = {s.strip().lower() for s in items if s and s.strip()}
    unknown = wanted - set(SCOPES)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown scope(s): {', '.join(sorted(unknown))}. Use: {', '.join(SCOPES)}.",
        )
    return [s for s in SCOPES if s == "read" or s in wanted]


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return authorization.strip() or None


def _device_principal(token: str) -> Principal:
    hashed = hash_secret(token)
    now = datetime.now(timezone.utc)
    with get_session() as session:
        row = session.exec(
            select(DeviceToken).where(DeviceToken.hashed_secret == hashed, DeviceToken.revoked_at.is_(None))
        ).first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked device token.")
        last = row.last_used_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or now - last >= _LAST_USED_RESOLUTION:
            row.last_used_at = now
            session.add(row)
            session.commit()
            session.refresh(row)
        return Principal("device", frozenset(row.scopes or ["read"]), user_id=row.user_id, device_id=row.id)


def authenticate(request: Request, authorization: str | None) -> Principal:
    token = _bearer(authorization)
    settings = get_settings()
    if token:
        if token.startswith(DEVICE_TOKEN_PREFIX):
            return _device_principal(token)
        if settings.admin_token and secrets.compare_digest(token, settings.admin_token):
            return Principal("admin", frozenset(SCOPES))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Use a device token (pair via /v1/companion/device/code) or the admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not settings.auth_enabled:
        # Localhost-open mode: the dashboard itself needs no login, so neither do these.
        return Principal("user", frozenset(SCOPES), user_id=None)
    user_id = request.session.get("user_id") if "session" in request.scope else None
    if user_id:
        return Principal("user", frozenset(SCOPES), user_id=int(user_id))
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Companion endpoints need a device token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_read(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    return authenticate(request, authorization)


async def require_control(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    principal = authenticate(request, authorization)
    if "control" not in principal.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This device token has read scope only; re-pair with control scope to change settings.",
        )
    return principal


def visible_key_ids(principal: Principal) -> list[int] | None:
    """Hub key ids this principal may see, or ``None`` for all of them."""
    if principal.sees_everything:
        return None
    from .storage.models import HubKey

    with get_session() as session:
        return list(session.exec(select(HubKey.id).where(HubKey.user_id == principal.user_id)).all())

"""Companion discovery and device pairing.

Public (no credential):

- ``GET  /v1/companion/info`` — hub version, API version and features, so a
  companion can adapt to whichever hub it finds before pairing.
- ``POST /v1/companion/device/code`` — start a pairing (RFC 8628 §3.1).
- ``POST /v1/companion/device/token`` — poll for the device token (RFC 8628 §3.4).

Device token (``read`` scope):

- ``GET /v1/live`` — Server-Sent Events of calls starting, producing their
  first token, changing activity and finishing. Metadata only.

Dashboard (session, see :mod:`..routers.spa_api`):

- ``GET  /api/companion/pairings/{user_code}`` — what is asking to pair.
- ``POST /api/companion/pairings/{user_code}/approve`` / ``/deny``.
- ``GET  /api/companion/devices`` and ``POST /api/companion/devices/{id}/revoke``.

The user approves in a dashboard they are already logged into, so pairing
needs no password on the device and works the same for a remote hub.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select

from ..auth import require_user
from ..companion_auth import (
    Principal,
    generate_device_token,
    hash_secret,
    normalize_scopes,
    require_read,
    visible_key_ids,
)
from ..live import get_bus, visible
from ..settings import get_settings
from ..storage.db import get_session
from ..storage.models import DevicePairing, DeviceToken, User, iso_utc

router = APIRouter()
dashboard_router = APIRouter()

#: Bumped when a companion-facing endpoint changes incompatibly.
COMPANION_API_VERSION = 1

#: Features a companion can rely on, by name. Endpoints add themselves here.
FEATURES: dict[str, str] = {
    "device_pairing": "/v1/companion/device/code",
    "live": "/v1/live",
    "limits": "/v1/limits",
    "spend": "/v1/spend",
}

#: Seconds between SSE keep-alive comments on an idle live stream.
HEARTBEAT_SECONDS = 15.0

DEVICE_CODE_TTL = timedelta(minutes=10)
POLL_INTERVAL = 5
MAX_PENDING = 20

GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
# RFC 8628 §6.1: a short, unambiguous alphabet (no vowels, no look-alikes).
_USER_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _new_user_code() -> str:
    raw = "".join(secrets.choice(_USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_user_code(code: str) -> str:
    raw = "".join(ch for ch in code.upper() if ch.isalnum())
    return f"{raw[:4]}-{raw[4:]}" if len(raw) == 8 else raw


async def _form_or_json(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}


def _oauth_error(error: str, description: str, code: int = status.HTTP_400_BAD_REQUEST) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=code)


# ---------------------------------------------------------------------------
# Public companion endpoints
# ---------------------------------------------------------------------------


@router.get("/companion/info")
def companion_info() -> dict[str, Any]:
    from ..main import __version__

    base = get_settings().base_url.rstrip("/")
    return {
        "service": "prompture-hub",
        "version": __version__,
        "api_version": COMPANION_API_VERSION,
        "features": dict(FEATURES),
        "pairing": {
            "device_authorization_endpoint": "/v1/companion/device/code",
            "token_endpoint": "/v1/companion/device/token",
            "verification_uri": f"{base}/app/pair",
            "scopes": ["read", "control"],
        },
    }


@router.post("/companion/device/code")
async def device_code(request: Request) -> dict[str, Any]:
    data = await _form_or_json(request)
    scopes = normalize_scopes(data.get("scope"))
    client_name = (str(data.get("client_name") or data.get("client_id") or "").strip() or None)
    now = _now()
    with get_session() as session:
        pending = session.exec(
            select(func.count(DevicePairing.id)).where(
                DevicePairing.status == "pending", DevicePairing.expires_at > now
            )
        ).one()
        if int(pending or 0) >= MAX_PENDING:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many pairings are waiting for approval; try again later.",
            )
        device_code = secrets.token_urlsafe(32)
        user_code = _new_user_code()
        while session.exec(select(DevicePairing).where(DevicePairing.user_code == user_code)).first():
            user_code = _new_user_code()
        session.add(
            DevicePairing(
                device_code_hash=hash_secret(device_code),
                user_code=user_code,
                client_name=client_name[:100] if client_name else None,
                requested_scopes=scopes,
                interval=POLL_INTERVAL,
                expires_at=now + DEVICE_CODE_TTL,
            )
        )
        session.commit()
    verification_uri = f"{get_settings().base_url.rstrip('/')}/app/pair"
    return {
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": verification_uri,
        "verification_uri_complete": f"{verification_uri}?code={user_code}",
        "expires_in": int(DEVICE_CODE_TTL.total_seconds()),
        "interval": POLL_INTERVAL,
    }


@router.post("/companion/device/token")
async def device_token(request: Request) -> Any:
    data = await _form_or_json(request)
    if data.get("grant_type") != GRANT_TYPE:
        return _oauth_error("unsupported_grant_type", f"grant_type must be {GRANT_TYPE}.")
    code = str(data.get("device_code") or "")
    if not code:
        return _oauth_error("invalid_request", "device_code is required.")
    now = _now()
    with get_session() as session:
        pairing = session.exec(
            select(DevicePairing).where(DevicePairing.device_code_hash == hash_secret(code))
        ).first()
        if pairing is None or pairing.status == "consumed":
            return _oauth_error("invalid_grant", "Unknown or already used device_code.")
        if _aware(pairing.expires_at) <= now:
            return _oauth_error("expired_token", "The pairing expired; start again.")
        if pairing.status == "denied":
            return _oauth_error("access_denied", "The pairing was denied in the dashboard.")
        if pairing.status == "pending":
            last = _aware(pairing.last_poll_at)
            pairing.last_poll_at = now
            too_fast = last is not None and (now - last).total_seconds() < pairing.interval
            if too_fast:
                pairing.interval += 5  # RFC 8628 §3.5: slow_down adds 5 seconds
            session.add(pairing)
            session.commit()
            if too_fast:
                return _oauth_error("slow_down", f"Poll at most every {pairing.interval} seconds.")
            return _oauth_error("authorization_pending", "Waiting for approval in the dashboard.")

        plaintext, hashed = generate_device_token()
        token = DeviceToken(
            name=pairing.approved_name or pairing.client_name or "companion",
            hashed_secret=hashed,
            scopes=pairing.approved_scopes or ["read"],
            user_id=pairing.approved_by,
        )
        session.add(token)
        session.flush()
        pairing.status = "consumed"
        pairing.token_id = token.id
        session.add(pairing)
        session.commit()
        return {
            "access_token": plaintext,
            "token_type": "Bearer",
            "scope": " ".join(token.scopes),
        }


# ---------------------------------------------------------------------------
# Live stream
# ---------------------------------------------------------------------------


def _sse_event(event: dict[str, Any]) -> str:
    lines = []
    if "id" in event:
        lines.append(f"id: {event['id']}")
    lines.append(f"event: {event['type']}")
    lines.append("data: " + json.dumps(event, separators=(",", ":"), default=str))
    return "\n".join(lines) + "\n\n"


@router.get("/live")
async def live_stream(
    request: Request,
    principal: Principal = Depends(require_read),
    after: int | None = Query(default=None, ge=0, description="Replay buffered events newer than this id."),
    limit: int | None = Query(default=None, ge=1, le=10000, description="Close after this many events."),
) -> StreamingResponse:
    """Stream live call events.

    On connect the client gets either the events it missed (when it sends
    ``Last-Event-ID`` or ``after``) or a ``snapshot`` of calls still running.
    If the client falls too far behind, a ``resync`` event tells it to fetch
    a fresh snapshot by reconnecting without an id.
    """
    key_ids = visible_key_ids(principal)
    bus = get_bus()
    header_id = request.headers.get("last-event-id")
    resume = int(header_id) if header_id and header_id.isdigit() else after
    # Subscribe before reading the buffer so nothing published in between is lost.
    sub = bus.subscribe()

    async def gen() -> AsyncIterator[str]:
        sent_id = 0
        count = 0

        def emit(event: dict[str, Any]) -> str | None:
            nonlocal sent_id, count
            if "id" in event:
                if event["id"] <= sent_id:
                    return None
                sent_id = event["id"]
            if not visible(event, key_ids):
                return None
            count += 1
            return _sse_event(event)

        try:
            yield "retry: 3000\n\n"
            if resume is not None:
                initial = bus.replay(resume)
            else:
                sent_id = bus.last_id()
                running = [e for e in bus.running() if visible(e, key_ids)]
                initial = [{"type": "snapshot", "running": running, "last_id": sent_id}]
            for event in initial:
                chunk = emit(event)
                if chunk:
                    yield chunk
                if limit and count >= limit:
                    return
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if sub.overflowed:
                    sub.overflowed = False
                    yield _sse_event({"type": "resync", "reason": "client fell behind"})
                chunk = emit(event)
                if chunk:
                    yield chunk
                if limit and count >= limit:
                    return
        finally:
            bus.unsubscribe(sub)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Dashboard approval + device management
# ---------------------------------------------------------------------------


def _load_pending(session: Any, user_code: str) -> DevicePairing:
    pairing = session.exec(
        select(DevicePairing).where(DevicePairing.user_code == normalize_user_code(user_code))
    ).first()
    if pairing is None or pairing.status != "pending" or _aware(pairing.expires_at) <= _now():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending pairing with that code.")
    return pairing


def _owner_id(user: User) -> int | None:
    return user.id if (get_settings().auth_enabled and user.id and user.id > 0) else None


@dashboard_router.get("/companion/pairings/{user_code}")
def get_pairing(user_code: str, user: User = Depends(require_user)) -> dict[str, Any]:
    with get_session() as session:
        pairing = _load_pending(session, user_code)
        return {
            "user_code": pairing.user_code,
            "client_name": pairing.client_name,
            "requested_scopes": pairing.requested_scopes,
            "expires_at": iso_utc(pairing.expires_at),
        }


class ApproveBody(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    scopes: list[str] | None = Field(default=None, description="Defaults to what the device asked for.")


@dashboard_router.post("/companion/pairings/{user_code}/approve")
def approve_pairing(user_code: str, body: ApproveBody, user: User = Depends(require_user)) -> dict[str, Any]:
    with get_session() as session:
        pairing = _load_pending(session, user_code)
        scopes = normalize_scopes(body.scopes if body.scopes is not None else pairing.requested_scopes)
        pairing.status = "approved"
        pairing.approved_scopes = scopes
        pairing.approved_name = (body.name or "").strip() or pairing.client_name or "companion"
        pairing.approved_by = _owner_id(user)
        session.add(pairing)
        session.commit()
        return {"status": "approved", "name": pairing.approved_name, "scopes": scopes}


@dashboard_router.post("/companion/pairings/{user_code}/deny", status_code=status.HTTP_204_NO_CONTENT)
def deny_pairing(user_code: str, user: User = Depends(require_user)) -> Response:
    with get_session() as session:
        pairing = _load_pending(session, user_code)
        pairing.status = "denied"
        session.add(pairing)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _serialize_device(t: DeviceToken) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "scopes": t.scopes or ["read"],
        "created_at": iso_utc(t.created_at),
        "last_used_at": iso_utc(t.last_used_at),
        "revoked_at": iso_utc(t.revoked_at),
        "active": t.revoked_at is None,
    }


@dashboard_router.get("/companion/devices")
def list_devices(user: User = Depends(require_user)) -> list[dict[str, Any]]:
    owner = _owner_id(user)
    with get_session() as session:
        stmt = select(DeviceToken).order_by(DeviceToken.created_at.desc())
        if owner is not None:
            stmt = stmt.where(DeviceToken.user_id == owner)
        return [_serialize_device(t) for t in session.exec(stmt).all()]


@dashboard_router.post("/companion/devices/{device_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_device(device_id: int, user: User = Depends(require_user)) -> Response:
    owner = _owner_id(user)
    with get_session() as session:
        token = session.get(DeviceToken, device_id)
        if token is None or (owner is not None and token.user_id != owner):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found.")
        if token.revoked_at is None:
            token.revoked_at = _now()
            session.add(token)
            session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

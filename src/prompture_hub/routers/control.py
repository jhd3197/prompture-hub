"""Key controls a companion (``control`` scope) or the dashboard can apply.

- ``POST  /v1/keys/{id}/pause`` / ``/resume`` — refuse or re-allow calls on a key.
- ``PATCH /v1/keys/{id}`` — change the spend cap / period, route override
  or default project.

Every change is announced as ``key.updated`` on the live stream so other
companions and dashboards refresh without polling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .. import live
from ..companion_auth import Principal, require_control, visible_key_ids
from ..metering import clean_project
from ..storage.db import get_session
from ..storage.models import HubKey, iso_utc

router = APIRouter()


class KeyControlPatch(BaseModel):
    daily_spend_cap_usd: float | None = Field(default=None, ge=0)
    spend_period: str | None = Field(default=None, pattern="^(day|week|month)$")
    route_override: str | None = Field(
        default=None, max_length=200, description="Model / combo to serve every chat call; empty string clears it."
    )
    default_project: str | None = Field(default=None, max_length=100, description="Empty string clears it.")


def _load(session: Any, key_id: int, principal: Principal) -> HubKey:
    key = session.get(HubKey, key_id)
    allowed = visible_key_ids(principal)
    if key is None or key.revoked_at is not None or (allowed is not None and key.id not in allowed):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")
    return key


def _state(key: HubKey) -> dict[str, Any]:
    return {
        "id": key.id,
        "name": key.name,
        "paused": key.paused_at is not None,
        "paused_at": iso_utc(key.paused_at),
        "route_override": key.route_override,
        "default_project": key.default_project,
        "daily_spend_cap_usd": key.daily_spend_cap_usd,
        "spend_period": key.spend_period,
    }


def _announce(key: HubKey, changes: dict[str, Any], principal: Principal) -> None:
    live.get_bus().publish(
        "key.updated",
        {"key_id": key.id, "key_name": key.name, "changes": changes, "by": principal.kind},
    )


def _set_paused(key_id: int, paused: bool, principal: Principal) -> dict[str, Any]:
    with get_session() as session:
        key = _load(session, key_id, principal)
        if (key.paused_at is not None) != paused:
            key.paused_at = datetime.now(timezone.utc) if paused else None
            session.add(key)
            session.commit()
            session.refresh(key)
            _announce(key, {"paused": paused}, principal)
        return _state(key)


@router.post("/keys/{key_id}/pause")
def pause_key(key_id: int, principal: Principal = Depends(require_control)) -> dict[str, Any]:
    return _set_paused(key_id, True, principal)


@router.post("/keys/{key_id}/resume")
def resume_key(key_id: int, principal: Principal = Depends(require_control)) -> dict[str, Any]:
    return _set_paused(key_id, False, principal)


@router.patch("/keys/{key_id}")
def update_key(key_id: int, body: KeyControlPatch, principal: Principal = Depends(require_control)) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "route_override" in changes:
        route = (changes["route_override"] or "").strip()
        if route and "/" not in route:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="route_override must be a model string like 'provider/model', 'combo/name' or 'auto/mode'.",
            )
        changes["route_override"] = route or None
    if "default_project" in changes:
        changes["default_project"] = clean_project(changes["default_project"])
    if changes.get("daily_spend_cap_usd", 0) is None or changes.get("spend_period", "day") is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cap and period cannot be cleared.")
    with get_session() as session:
        key = _load(session, key_id, principal)
        for name, value in changes.items():
            setattr(key, name, value)
        session.add(key)
        session.commit()
        session.refresh(key)
        if changes:
            _announce(key, changes, principal)
        return _state(key)

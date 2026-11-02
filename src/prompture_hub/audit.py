"""Audit trail for key changes. Details must never contain secrets."""

from __future__ import annotations

from typing import Any

from .companion_auth import Principal
from .storage.db import get_session
from .storage.models import AuditLog, DeviceToken, User

# Actor for the /admin router, which is gated by the admin token alone.
ADMIN_ACTOR = Principal("admin")
ADMIN_LABEL = "admin token"
LOCAL_LABEL = "local dashboard"


def actor_label(principal: Principal) -> str:
    """Human-readable name: admin token, the device's name, the user's email or the open dashboard."""
    if principal.kind == "admin":
        return ADMIN_LABEL
    with get_session() as session:
        if principal.kind == "device" and principal.device_id is not None:
            row = session.get(DeviceToken, principal.device_id)
            return row.name if row else f"device #{principal.device_id}"
        if principal.user_id is not None:
            row = session.get(User, principal.user_id)
            return row.email if row else f"user #{principal.user_id}"
    return LOCAL_LABEL


def record(
    principal: Principal, action: str, key_id: int | None = None, details: dict[str, Any] | None = None
) -> None:
    actor_id = principal.device_id if principal.kind == "device" else principal.user_id
    label = actor_label(principal)
    with get_session() as session:
        session.add(
            AuditLog(
                actor_kind=principal.kind,
                actor_id=actor_id,
                actor_label=label,
                action=action,
                key_id=key_id,
                details=details or {},
            )
        )
        session.commit()

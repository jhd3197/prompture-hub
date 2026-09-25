"""Alert rules and fired alerts.

Dashboard (session):

- ``GET/POST /api/alerts/rules``, ``PATCH/DELETE /api/alerts/rules/{id}``
- ``GET /api/alerts`` — recent alerts; ``POST /api/alerts/{id}/ack``

Companion (device token):

- ``GET /v1/alerts`` (``read``) and ``POST /v1/alerts/{id}/ack`` (``control``)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import select

from ..alerts import KINDS, default_threshold, serialize_event
from ..auth import require_user
from ..companion_auth import Principal, require_control, require_read
from ..settings import get_settings
from ..storage.db import get_session
from ..storage.models import AlertEvent, AlertRule, HubKey, User, iso_utc

router = APIRouter()
dashboard_router = APIRouter()


def _owner(user: User) -> int | None:
    return user.id if (get_settings().auth_enabled and user.id and user.id > 0) else None


def _principal_owner(principal: Principal) -> int | None:
    return None if principal.sees_everything else principal.user_id


def _check_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        raise ValueError("must be an http(s) URL")
    return value


class RuleBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str
    threshold: float | None = None
    key_id: int | None = None
    target: str | None = Field(default=None, max_length=200)
    webhook_url: str | None = Field(default=None, max_length=500)
    ntfy_url: str | None = Field(default=None, max_length=500)
    cooldown_minutes: int = Field(default=60, ge=0, le=60 * 24 * 7)
    enabled: bool = True

    @field_validator("webhook_url", "ntfy_url")
    @classmethod
    def _urls(cls, value: str | None) -> str | None:
        return _check_url(value)


class RulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    threshold: float | None = None
    key_id: int | None = None
    target: str | None = Field(default=None, max_length=200)
    webhook_url: str | None = Field(default=None, max_length=500)
    ntfy_url: str | None = Field(default=None, max_length=500)
    cooldown_minutes: int | None = Field(default=None, ge=0, le=60 * 24 * 7)
    enabled: bool | None = None

    @field_validator("webhook_url", "ntfy_url")
    @classmethod
    def _urls(cls, value: str | None) -> str | None:
        return _check_url(value)


def _validate(kind: str, threshold: float | None, key_id: int | None, owner: int | None) -> float | None:
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of: {', '.join(KINDS)}.")
    if kind in ("key_spend", "provider_headroom"):
        threshold = default_threshold(kind) if threshold is None else threshold
        if not 0 < threshold <= 1:
            raise HTTPException(status_code=400, detail=f"{kind} threshold is a fraction between 0 and 1.")
    elif kind == "balance_low":
        if threshold is None or threshold < 0:
            raise HTTPException(status_code=400, detail="balance_low needs a threshold amount of 0 or more.")
    else:
        threshold = None
    if key_id is not None:
        with get_session() as session:
            key = session.get(HubKey, key_id)
        if key is None or (owner is not None and key.user_id != owner):
            raise HTTPException(status_code=404, detail="Key not found.")
    return threshold


def _serialize_rule(rule: AlertRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "kind": rule.kind,
        "threshold": rule.threshold,
        "key_id": rule.key_id,
        "target": rule.target,
        "webhook_url": rule.webhook_url,
        "ntfy_url": rule.ntfy_url,
        "cooldown_minutes": rule.cooldown_minutes,
        "enabled": rule.enabled,
        "created_at": iso_utc(rule.created_at),
    }


def _load_rule(session: Any, rule_id: int, owner: int | None) -> AlertRule:
    rule = session.get(AlertRule, rule_id)
    if rule is None or (owner is not None and rule.user_id != owner):
        raise HTTPException(status_code=404, detail="Alert rule not found.")
    return rule


@dashboard_router.get("/alerts/rules")
def list_rules(user: User = Depends(require_user)) -> list[dict[str, Any]]:
    owner = _owner(user)
    with get_session() as session:
        stmt = select(AlertRule).order_by(AlertRule.created_at)
        if owner is not None:
            stmt = stmt.where(AlertRule.user_id == owner)
        return [_serialize_rule(r) for r in session.exec(stmt).all()]


@dashboard_router.post("/alerts/rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleBody, user: User = Depends(require_user)) -> dict[str, Any]:
    owner = _owner(user)
    threshold = _validate(body.kind, body.threshold, body.key_id, owner)
    rule = AlertRule(**body.model_dump(exclude={"threshold"}), threshold=threshold, user_id=owner)
    with get_session() as session:
        session.add(rule)
        session.commit()
        session.refresh(rule)
        return _serialize_rule(rule)


@dashboard_router.patch("/alerts/rules/{rule_id}")
def update_rule(rule_id: int, body: RulePatch, user: User = Depends(require_user)) -> dict[str, Any]:
    owner = _owner(user)
    changes = body.model_dump(exclude_unset=True)
    with get_session() as session:
        rule = _load_rule(session, rule_id, owner)
        if "threshold" in changes or "key_id" in changes:
            changes["threshold"] = _validate(
                rule.kind, changes.get("threshold", rule.threshold), changes.get("key_id", rule.key_id), owner
            )
        for name, value in changes.items():
            setattr(rule, name, value)
        session.add(rule)
        session.commit()
        session.refresh(rule)
        return _serialize_rule(rule)


@dashboard_router.delete("/alerts/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, user: User = Depends(require_user)) -> Response:
    with get_session() as session:
        rule = _load_rule(session, rule_id, _owner(user))
        for event in session.exec(select(AlertEvent).where(AlertEvent.rule_id == rule.id)).all():
            session.delete(event)
        session.delete(rule)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _list_events(owner: int | None, unacknowledged: bool, limit: int) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = select(AlertEvent, AlertRule).join(AlertRule, AlertEvent.rule_id == AlertRule.id)
        if owner is not None:
            stmt = stmt.where(AlertRule.user_id == owner)
        if unacknowledged:
            stmt = stmt.where(AlertEvent.acknowledged_at.is_(None))
        stmt = stmt.order_by(AlertEvent.created_at.desc(), AlertEvent.id.desc()).limit(limit)
        return [serialize_event(event, rule) for event, rule in session.exec(stmt).all()]


def _ack(alert_id: int, owner: int | None) -> dict[str, Any]:
    with get_session() as session:
        event = session.get(AlertEvent, alert_id)
        rule = session.get(AlertRule, event.rule_id) if event else None
        if event is None or rule is None or (owner is not None and rule.user_id != owner):
            raise HTTPException(status_code=404, detail="Alert not found.")
        if event.acknowledged_at is None:
            event.acknowledged_at = datetime.now(timezone.utc)
            session.add(event)
            session.commit()
            session.refresh(event)
        return serialize_event(event, rule)


@dashboard_router.get("/alerts")
def list_alerts(
    user: User = Depends(require_user),
    unacknowledged: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    return _list_events(_owner(user), unacknowledged, limit)


@dashboard_router.post("/alerts/{alert_id}/ack")
def ack_alert_dashboard(alert_id: int, user: User = Depends(require_user)) -> dict[str, Any]:
    return _ack(alert_id, _owner(user))


@router.get("/alerts")
def list_alerts_companion(
    principal: Principal = Depends(require_read),
    unacknowledged: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    return _list_events(_principal_owner(principal), unacknowledged, limit)


@router.post("/alerts/{alert_id}/ack")
def ack_alert_companion(alert_id: int, principal: Principal = Depends(require_control)) -> dict[str, Any]:
    return _ack(alert_id, _principal_owner(principal))

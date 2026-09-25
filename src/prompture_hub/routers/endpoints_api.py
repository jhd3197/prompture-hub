"""Dashboard API for custom OpenAI-compatible endpoints.

- ``GET/POST /api/endpoints``, ``PATCH/DELETE /api/endpoints/{id}``
- ``POST /api/endpoints/{id}/check`` — probe reachability, latency and models
- ``GET  /api/endpoints/{id}/usage?days=N`` — daily history of calls it served
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlmodel import select

from .. import endpoints
from ..auth import require_user
from ..settings import get_settings
from ..storage.db import get_session
from ..storage.models import CustomEndpoint, UsageRecord, User, iso_utc
from .analytics import _Bucket

router = APIRouter()

_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")


def _owner(user: User) -> int | None:
    return user.id if (get_settings().auth_enabled and user.id and user.id > 0) else None


def _check_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ValueError("must be an http(s) URL")
    return value


def _check_env(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    if not _ENV_RE.match(value.strip()):
        raise ValueError("must be an environment variable name, e.g. MY_ENDPOINT_KEY")
    return value.strip()


class EndpointBody(BaseModel):
    name: str = Field(description="Lowercase slug used in model strings: openai_compatible/<name>/<model>.")
    base_url: str = Field(max_length=500, description="Base URL up to /v1, e.g. http://localhost:8001/v1")
    api_key_env: str | None = Field(default=None, description="Name of the env var holding the API key, if any.")

    @field_validator("base_url")
    @classmethod
    def _base(cls, value: str) -> str:
        return _check_base_url(value)

    @field_validator("api_key_env")
    @classmethod
    def _env(cls, value: str | None) -> str | None:
        return _check_env(value)


class EndpointPatch(BaseModel):
    base_url: str | None = Field(default=None, max_length=500)
    api_key_env: str | None = None

    @field_validator("base_url")
    @classmethod
    def _base(cls, value: str | None) -> str | None:
        return None if value is None else _check_base_url(value)

    @field_validator("api_key_env")
    @classmethod
    def _env(cls, value: str | None) -> str | None:
        return _check_env(value)


def _serialize(row: CustomEndpoint) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "base_url": row.base_url,
        "api_key_env": row.api_key_env,
        "model_prefix": endpoints.model_prefix(row.name),
        "models": row.models or [],
        "last_status": row.last_status,
        "last_latency_ms": row.last_latency_ms,
        "last_checked_at": iso_utc(row.last_checked_at),
        "created_at": iso_utc(row.created_at),
    }


def _load(session: Any, endpoint_id: int, owner: int | None) -> CustomEndpoint:
    row = session.get(CustomEndpoint, endpoint_id)
    if row is None or (owner is not None and row.user_id != owner):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found.")
    return row


@router.get("/endpoints")
def list_endpoints(user: User = Depends(require_user)) -> list[dict[str, Any]]:
    owner = _owner(user)
    with get_session() as session:
        stmt = select(CustomEndpoint).order_by(CustomEndpoint.name)
        if owner is not None:
            stmt = stmt.where(CustomEndpoint.user_id == owner)
        return [_serialize(r) for r in session.exec(stmt).all()]


@router.post("/endpoints", status_code=status.HTTP_201_CREATED)
def create_endpoint(body: EndpointBody, user: User = Depends(require_user)) -> dict[str, Any]:
    name = body.name.strip().lower()
    if not endpoints.NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="name must be 1-40 lowercase letters, digits or dashes.")
    if name in endpoints.BUILTIN_PROFILES:
        raise HTTPException(status_code=409, detail=f"'{name}' is a built-in Prompture profile.")
    with get_session() as session:
        if session.exec(select(CustomEndpoint).where(CustomEndpoint.name == name)).first():
            raise HTTPException(status_code=409, detail=f"An endpoint named '{name}' already exists.")
        row = CustomEndpoint(name=name, base_url=body.base_url, api_key_env=body.api_key_env, user_id=_owner(user))
        session.add(row)
        session.commit()
        session.refresh(row)
    endpoints.register(row)
    return _serialize(row)


@router.patch("/endpoints/{endpoint_id}")
def update_endpoint(endpoint_id: int, body: EndpointPatch, user: User = Depends(require_user)) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    with get_session() as session:
        row = _load(session, endpoint_id, _owner(user))
        for name, value in changes.items():
            if name == "base_url" and value is None:
                continue
            setattr(row, name, value)
        session.add(row)
        session.commit()
        session.refresh(row)
    endpoints.register(row)
    return _serialize(row)


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(endpoint_id: int, user: User = Depends(require_user)) -> Response:
    with get_session() as session:
        row = _load(session, endpoint_id, _owner(user))
        name = row.name
        session.delete(row)
        session.commit()
    endpoints.unregister(name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/endpoints/{endpoint_id}/check")
async def check_endpoint(endpoint_id: int, user: User = Depends(require_user)) -> dict[str, Any]:
    with get_session() as session:
        row = _load(session, endpoint_id, _owner(user))
    result = await run_in_threadpool(endpoints.check, row)
    updated = endpoints.apply_check(endpoint_id, result)
    return {**_serialize(updated), "detail": result["detail"]}


@router.get("/endpoints/{endpoint_id}/usage")
def endpoint_usage(
    endpoint_id: int,
    days: int = Query(default=7, ge=1, le=90),
    user: User = Depends(require_user),
) -> dict[str, Any]:
    """Daily history of calls served by this endpoint (requested directly or via a route)."""
    with get_session() as session:
        row = _load(session, endpoint_id, _owner(user))
        prefix = endpoints.model_prefix(row.name)
        start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        rows = session.exec(
            select(UsageRecord).where(
                UsageRecord.timestamp >= start,
                or_(UsageRecord.model.startswith(prefix), UsageRecord.served_by.startswith(prefix)),
            )
        ).all()
    totals = _Bucket()
    by_day: dict[str, _Bucket] = defaultdict(_Bucket)
    by_model: dict[str, _Bucket] = defaultdict(_Bucket)
    for u in rows:
        ts = u.timestamp if u.timestamp.tzinfo else u.timestamp.replace(tzinfo=timezone.utc)
        totals.add(u)
        by_day[ts.date().isoformat()].add(u)
        served = u.served_by if (u.served_by or "").startswith(prefix) else u.model
        by_model[served[len(prefix):]].add(u)
    day_list = []
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        day_list.append({"date": d, **(by_day[d] if d in by_day else _Bucket()).to_dict()})
    return {
        "endpoint": row.name,
        "range": {"start": iso_utc(start), "days": days},
        "totals": totals.to_dict(),
        "by_day": day_list,
        "by_model": sorted(
            ({"model": m, **b.to_dict()} for m, b in by_model.items()), key=lambda r: -r["requests"]
        ),
    }

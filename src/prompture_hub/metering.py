"""One place that meters a call: usage row, project attribution, route stats.

Every metered endpoint records through :func:`record`, so the usage table,
the live event stream and alert rules all see the same facts about a call.

Projects
--------
A call is attributed to a project from, in order:

1. the ``X-Project`` request header (what ``prompture-hub setup --project``
   configures in each tool), then
2. the calling key's ``default_project``.

Project names are free-form labels, trimmed and capped at
:data:`MAX_PROJECT_LEN` characters; an empty value means "no project".
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request

from .auth import require_hub_key
from .storage.db import get_session
from .storage.models import HubKey, UsageRecord

PROJECT_HEADER = "X-Project"
MAX_PROJECT_LEN = 100


def clean_project(value: str | None) -> str | None:
    """Normalize a project label: printable, trimmed, bounded; ``None`` when empty."""
    if value is None:
        return None
    cleaned = "".join(ch for ch in str(value) if ch.isprintable()).strip()
    return cleaned[:MAX_PROJECT_LEN] or None


def resolve_project(request: Request | None, key: HubKey | None) -> str | None:
    header = request.headers.get(PROJECT_HEADER) if request is not None else None
    return clean_project(header) or clean_project(getattr(key, "default_project", None))


async def request_project(request: Request, key: HubKey = Depends(require_hub_key)) -> str | None:
    """FastAPI dependency: the project this request is attributed to.

    Shares the cached ``require_hub_key`` result with the endpoint's own key
    dependency, so it adds no extra lookup.
    """
    return resolve_project(request, key)


def route_facts(meta: dict[str, Any] | None) -> tuple[str | None, int, dict[str, Any]]:
    """``(served_by, upstream attempts, route)`` from a driver result's ``meta``."""
    route = (meta or {}).get("route") or {}
    served_by = route.get("served_by")
    attempts = sum(1 for a in route.get("attempts", []) if a.get("outcome") in ("ok", "error"))
    return served_by, max(attempts, 1), route


def record(
    *,
    key_id: int,
    model: str,
    endpoint: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost: float = 0.0,
    latency_ms: int = 0,
    status: str = "ok",
    error: str | None = None,
    project: str | None = None,
    meta: dict[str, Any] | None = None,
) -> UsageRecord:
    """Write one usage row for a finished (or rejected) call and return it."""
    served_by, attempts, _route = route_facts(meta)
    row = UsageRecord(
        key_id=key_id,
        model=model or "",
        endpoint=endpoint,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        status=status,
        error=error,
        served_by=served_by,
        attempts=attempts,
        project=clean_project(project),
    )
    with get_session() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row

"""One place that meters a call: usage row, project attribution, live events.

Every metered endpoint records through :func:`record`, so the usage table,
the live event stream and alert rules all see the same facts about a call.
Endpoints that want the call to show up as *running* open it first with
:func:`begin` and pass the returned :class:`Call` to :func:`record`.

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

import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Request

from . import live
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


@dataclass
class Call:
    """A metered call in progress; feeds the live stream until it is recorded."""

    key_id: int
    model: str
    endpoint: str
    project: str | None = None
    stream: bool = False
    request_id: str = field(default_factory=live.new_request_id)
    started: float = field(default_factory=time.perf_counter)
    first_token_ms: int | None = None
    activity: str | None = None
    finished: bool = False

    def _base(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "key_id": self.key_id}

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def mark_first_token(self) -> None:
        if self.first_token_ms is None and not self.finished:
            self.first_token_ms = self.elapsed_ms()
            live.get_bus().publish("request.first_token", {**self._base(), "ttft_ms": self.first_token_ms})

    def mark_activity(self, state: str, event: str | None = None) -> None:
        """``state`` is ``working`` or ``waiting`` (e.g. an agent asked a question)."""
        if state != self.activity and not self.finished:
            self.activity = state
            live.get_bus().publish("request.activity", {**self._base(), "state": state, "event": event})

    def close(self) -> None:
        """End a call that never reached :func:`record` (e.g. the client disconnected)."""
        if not self.finished:
            self.finished = True
            live.get_bus().publish(
                "request.finished",
                {**self._base(), "model": self.model, "endpoint": self.endpoint, "project": self.project,
                 "status": "disconnected", "latency_ms": self.elapsed_ms()},
            )


def begin(key: HubKey, model: str, endpoint: str, project: str | None = None, *, stream: bool = False) -> Call:
    """Open a call and announce it on the live stream."""
    call = Call(key_id=key.id, model=model, endpoint=endpoint, project=clean_project(project), stream=stream)
    live.get_bus().publish(
        "request.started",
        {
            **call._base(),
            "key_name": key.name,
            "model": call.model,
            "endpoint": endpoint,
            "project": call.project,
            "stream": stream,
        },
    )
    return call


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
    call: Call | None = None,
) -> UsageRecord:
    """Write one usage row for a finished (or rejected) call and return it."""
    served_by, attempts, route = route_facts(meta)
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
    if call is not None:
        call.finished = True
    _publish_finished(row, call, route)
    return row


def _publish_finished(row: UsageRecord, call: Call | None, route: dict[str, Any]) -> None:
    live.get_bus().publish(
        "request.finished",
        {
            "request_id": call.request_id if call else live.new_request_id(),
            "key_id": row.key_id,
            "model": row.model,
            "served_by": row.served_by,
            "endpoint": row.endpoint,
            "project": row.project,
            "status": row.status,
            "error": (row.error or "")[:200] or None,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "cost_usd": row.cost_usd,
            "latency_ms": row.latency_ms,
            "ttft_ms": call.first_token_ms if call else None,
            "attempts": row.attempts,
            "fallback": row.attempts > 1,
            "deprioritized": route.get("deprioritized") or [],
        },
    )

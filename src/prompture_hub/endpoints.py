"""Custom OpenAI-compatible endpoints: registration and health checks.

A :class:`~.storage.models.CustomEndpoint` row is registered with Prompture
as an OpenAI-compatible *profile*, so ``openai_compatible/<name>/<model>``
routes to it through Prompture's generic driver and every call is metered
like any built-in provider. Registration happens at startup and whenever an
endpoint is created, changed or removed.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlmodel import select

from .storage.db import get_session
from .storage.models import CustomEndpoint

logger = logging.getLogger("prompture_hub.endpoints")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MODEL_PREFIX = "openai_compatible"
#: A health check answering slower than this is reported as ``slow``.
SLOW_MS = 2000


def _profiles() -> dict[str, dict[str, str]]:
    from prompture.drivers.openai_compatible_driver import OPENAI_COMPATIBLE_PROFILES

    return OPENAI_COMPATIBLE_PROFILES


# Profiles Prompture ships with; custom endpoints may not shadow them.
BUILTIN_PROFILES = frozenset(_profiles())


def model_prefix(name: str) -> str:
    return f"{MODEL_PREFIX}/{name}/"


def register(endpoint: CustomEndpoint) -> None:
    _profiles()[endpoint.name] = {"endpoint": endpoint.base_url.rstrip("/"), "env_var": endpoint.api_key_env or ""}


def unregister(name: str) -> None:
    if name not in BUILTIN_PROFILES:
        _profiles().pop(name, None)


def sync_all() -> int:
    """Register every stored endpoint with Prompture. Returns how many."""
    with get_session() as session:
        rows = session.exec(select(CustomEndpoint)).all()
    for row in rows:
        register(row)
    return len(rows)


def check(endpoint: CustomEndpoint, client: httpx.Client | None = None) -> dict[str, Any]:
    """Probe ``GET {base_url}/models``: reachability, latency and served models."""
    headers = {}
    key = os.environ.get(endpoint.api_key_env) if endpoint.api_key_env else None
    if key:
        headers["Authorization"] = f"Bearer {key}"
    owned = client is None
    http = client or httpx.Client(timeout=10.0, follow_redirects=False)
    started = time.perf_counter()
    models: list[str] | None = None
    try:
        response = http.get(endpoint.base_url.rstrip("/") + "/models", headers=headers)
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code == 200:
            data = response.json().get("data") or []
            models = sorted({str(m["id"]) for m in data if isinstance(m, dict) and m.get("id")})
            status = "slow" if latency > SLOW_MS else "online"
            detail = None
        else:
            status, detail = "error", f"HTTP {response.status_code}"
    except (httpx.HTTPError, ValueError) as exc:
        latency = int((time.perf_counter() - started) * 1000)
        status, detail = "unreachable", type(exc).__name__
    finally:
        if owned:
            http.close()
    return {"status": status, "latency_ms": latency, "models": models, "detail": detail}


def apply_check(endpoint_id: int, result: dict[str, Any]) -> CustomEndpoint | None:
    with get_session() as session:
        row = session.get(CustomEndpoint, endpoint_id)
        if row is None:
            return None
        row.last_status = result["status"]
        row.last_latency_ms = result["latency_ms"]
        row.last_checked_at = datetime.now(timezone.utc)
        if result.get("models") is not None:
            row.models = result["models"]
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def served_models() -> list[str]:
    """Model strings for every model a registered endpoint last reported."""
    with get_session() as session:
        rows = session.exec(select(CustomEndpoint).order_by(CustomEndpoint.name)).all()
    return [model_prefix(r.name) + m for r in rows for m in (r.models or [])]

"""POST /v1/coding-agents/run — invoke a local coding-agent CLI through the hub.

Wraps :func:`prompture.run_coding_agent`. The hub adds:

- Auth via the calling hub key (``Authorization: Bearer ph_…``).
- Quota enforcement (spend cap + rate limit) before any subprocess starts.
- A workspace guardrail: ``cwd`` must resolve under ``HUB_AGENT_WORKSPACE``
  so an over-permissioned client can't ``cwd=/`` the operator's box.
- A yolo guardrail: ``approval_mode='yolo'`` is refused unless
  ``HUB_ALLOW_AGENT_YOLO`` is set, since yolo lets the agent run arbitrary
  shell commands without prompting.
- A UsageRecord per run so the dashboard sees agent cost + latency next
  to chat completions and extractions.

Prompture does the actual subprocess management. The hub does not
sandbox the agent beyond the cwd check — operators should still treat
the workspace as untrusted output and not, say, mount their home dir
into it.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..quotas import enforce_quotas
from ..settings import get_settings
from ..storage.db import get_session
from ..storage.models import HubKey, UsageRecord

router = APIRouter()


class RunAgentRequest(BaseModel):
    agent: str = Field(description="Agent id, e.g. 'claude', 'codex', 'aider'.")
    task: str = Field(min_length=1, description="The instruction to send.")
    approval_mode: str = Field(
        default="default",
        description="default | auto | yolo. yolo requires HUB_ALLOW_AGENT_YOLO.",
    )
    model: str | None = Field(
        default=None,
        description="Override the model the agent uses (CLI-dependent).",
    )
    extra_args: list[str] = Field(default_factory=list)
    output_format: str = Field(default="text", description="text | json.")
    session_id: str | None = Field(
        default=None,
        description="When set, resume a prior session (agent must support it).",
    )
    cwd: str | None = Field(
        default=None,
        description=(
            "Relative path under HUB_AGENT_WORKSPACE to run inside. "
            "Defaults to the workspace root."
        ),
    )
    timeout: int | None = Field(
        default=None, description="Override HUB_AGENT_DEFAULT_TIMEOUT for this run.",
    )


def _resolve_workspace_cwd(requested: str | None) -> str:
    """Resolve ``requested`` against the configured workspace, refusing
    paths that try to escape via ``..`` symlinks etc."""
    settings = get_settings()
    workspace = Path(settings.agent_workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    if not requested or requested in (".", "./"):
        return str(workspace)

    candidate = (workspace / requested).expanduser().resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"cwd '{requested}' escapes the configured workspace "
                f"'{workspace}'. Adjust HUB_AGENT_WORKSPACE or pick a subpath."
            ),
        ) from exc

    candidate.mkdir(parents=True, exist_ok=True)
    return str(candidate)


def _serialize_events(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in raw or []:
        if hasattr(ev, "__dict__"):
            out.append({k: v for k, v in vars(ev).items() if not k.startswith("_")})
        else:
            out.append({"raw": str(ev)})
    return out


def execute_run(body: RunAgentRequest) -> tuple[dict[str, Any], int, int, float]:
    """Shared run path used by both /v1/coding-agents/run (hub-key auth +
    metering) and /api/agents/run (session auth, console mode, no metering).

    Returns ``(response_dict, prompt_tokens, completion_tokens, cost_usd)``
    so the caller can decide whether to write a UsageRecord.
    """
    settings = get_settings()

    if body.approval_mode == "yolo" and not settings.allow_agent_yolo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "approval_mode='yolo' is disabled on this hub. "
                "Set HUB_ALLOW_AGENT_YOLO=true to enable, then restart."
            ),
        )

    cwd = _resolve_workspace_cwd(body.cwd)
    timeout = body.timeout or settings.agent_default_timeout

    try:
        from prompture import run_coding_agent  # type: ignore[attr-defined]
    except ImportError:  # pragma: no cover
        from prompture.infra.coding_agents import run_coding_agent  # type: ignore

    try:
        result = run_coding_agent(
            body.agent,
            body.task,
            cwd=cwd,
            approval_mode=body.approval_mode,  # type: ignore[arg-type]
            model=body.model,
            extra_args=body.extra_args or None,
            timeout=timeout,
            output_format=body.output_format,  # type: ignore[arg-type]
            session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc),
        ) from exc

    prompt_tok = int(getattr(result, "input_tokens", 0) or 0)
    completion_tok = int(getattr(result, "output_tokens", 0) or 0)
    cost = float(getattr(result, "cost_usd", 0.0) or 0.0)

    response = {
        "agent": result.agent,
        "command": result.command,
        "cwd": result.cwd,
        "returncode": result.returncode,
        "duration_seconds": result.duration_seconds,
        "output": result.output,
        "events": _serialize_events(getattr(result, "events", None)),
        "usage": {
            "prompt_tokens": prompt_tok,
            "completion_tokens": completion_tok,
            "total_tokens": prompt_tok + completion_tok,
            "cost_usd": cost,
        },
    }
    return response, prompt_tok, completion_tok, cost


@router.post("/coding-agents/run")
async def run_agent(
    body: RunAgentRequest,
    key: HubKey = Depends(enforce_quotas),
) -> dict[str, Any]:
    endpoint = "/v1/coding-agents/run"
    started = time.perf_counter()
    try:
        response, prompt_tok, completion_tok, cost = execute_run(body)
    except HTTPException as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _record(
            key.id, body.agent, endpoint, 0, 0, 0.0, elapsed_ms,
            "error", str(exc.detail),
        )
        raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    run_status = "ok" if response["returncode"] == 0 else "error"
    _record(
        key.id, body.agent, endpoint,
        prompt_tok, completion_tok, cost, elapsed_ms,
        run_status,
        response["output"][:500] if run_status == "error" else None,
    )
    return response


def _record(
    key_id: int,
    model: str,
    endpoint: str,
    prompt_tok: int,
    completion_tok: int,
    cost: float,
    elapsed_ms: int,
    status_str: str,
    error: str | None,
) -> None:
    with get_session() as session:
        session.add(
            UsageRecord(
                key_id=key_id,
                model=model,
                endpoint=endpoint,
                prompt_tokens=prompt_tok,
                completion_tokens=completion_tok,
                total_tokens=prompt_tok + completion_tok,
                cost_usd=cost,
                latency_ms=elapsed_ms,
                status=status_str,
                error=error,
            )
        )
        session.commit()

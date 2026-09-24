"""Anthropic-compatible endpoints — what Claude Code and the Anthropic SDKs call.

- ``POST /v1/messages`` — any Prompture model (``combo/…``, ``auto/…`` and
  aliases included) behind the Messages API, streaming and tools supported.
- ``POST /v1/messages/count_tokens`` — provider count when available,
  otherwise a rough estimate.

Both accept the hub key as ``x-api-key`` (``ANTHROPIC_API_KEY``) or
``Authorization: Bearer`` (``ANTHROPIC_AUTH_TOKEN``). Wire-format
translation lives in :mod:`prompture.gateway.anthropic_format`.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from prompture.gateway import (
    SSE_HEADERS,
    ChatOutcome,
    anthropic_message,
    anthropic_sse,
    anthropic_to_driver,
    estimate_input_tokens,
    live_events_for,
    run_chat,
    stream_anthropic_events,
)

from ..auth import require_hub_key
from ..quotas import enforce_quotas
from ..storage.models import HubKey
from .openai_compat import _record

router = APIRouter()

_ENDPOINT = "/v1/messages"


def resolve_model(name: str) -> str:
    """Bare Anthropic model ids (``claude-sonnet-4-5``) map to Prompture's
    ``claude/`` driver; ``provider/model``, combos, ``auto/`` and aliases pass through."""
    if "/" in name:
        return name
    from prompture.resilience import list_model_aliases

    if name in list_model_aliases():
        return name
    return f"claude/{name}"


def _check_allowed(key: HubKey, requested: str, resolved: str) -> None:
    if key.allowed_models and requested not in key.allowed_models and resolved not in key.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{requested}' is not in this key's allowed_models whitelist.",
        )


@router.post("/messages")
async def messages(request: Request, key: HubKey = Depends(enforce_quotas)):
    body: dict[str, Any] = await request.json()
    requested = str(body.get("model") or "")
    if not requested:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model is required.")
    model = resolve_model(requested)
    _check_allowed(key, requested, model)
    msgs, tools, options = anthropic_to_driver(body)

    from prompture.drivers import get_driver_for_model

    driver = get_driver_for_model(model)
    started = time.perf_counter()

    def record(outcome: ChatOutcome) -> None:
        usage = outcome.usage
        _record(
            key.id, requested, usage["prompt_tokens"], usage["completion_tokens"], outcome.cost,
            int((time.perf_counter() - started) * 1000),
            "error" if outcome.error else "ok",
            str(outcome.error) if outcome.error else None,
            endpoint=_ENDPOINT,
            route=outcome.meta.get("route") or {"attempts": getattr(outcome.error, "attempts", None) or []},
        )

    if body.get("stream"):
        def event_gen() -> Iterator[str]:
            events = stream_anthropic_events(
                live_events_for(driver, msgs, tools, options), model=requested, on_complete=record,
            )
            for name, data in events:
                yield anthropic_sse(name, data)

        return StreamingResponse(event_gen(), media_type="text/event-stream", headers=SSE_HEADERS)

    try:
        outcome = await run_in_threadpool(run_chat, driver, msgs, options, tools=tools or None)
    except NotImplementedError as exc:
        record(ChatOutcome(error=exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        record(ChatOutcome(error=exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    record(outcome)
    return anthropic_message(outcome, model=requested)


@router.post("/messages/count_tokens")
async def count_tokens(request: Request, key: HubKey = Depends(require_hub_key)) -> dict[str, int]:
    body: dict[str, Any] = await request.json()
    requested = str(body.get("model") or "")
    model = resolve_model(requested) if requested else ""
    _check_allowed(key, requested, model)
    msgs, tools, options = anthropic_to_driver(body)

    def count() -> int:
        if "/" in model and not model.startswith(("combo/", "auto/")):
            try:
                from prompture.infra.token_counting import count_request_tokens

                return int(count_request_tokens(model, msgs, tools=tools or None, options=options).input_tokens)
            except Exception:  # noqa: S110 - providers without a counting API fall back to the estimate
                pass
        return estimate_input_tokens(msgs, tools)

    return {"input_tokens": await run_in_threadpool(count)}

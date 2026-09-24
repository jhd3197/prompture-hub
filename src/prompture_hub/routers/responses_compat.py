"""OpenAI Responses API: ``POST /v1/responses`` (what Codex CLI speaks).

Stateless: ``previous_response_id`` is rejected — clients send the full
``input`` each turn (Codex does). Translation lives in
:mod:`prompture.gateway.responses_format`.
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
    live_events_for,
    response_object,
    responses_sse,
    responses_to_driver,
    run_chat,
    stream_responses_events,
)

from ..quotas import enforce_quotas
from ..storage.models import HubKey
from .openai_compat import _record

router = APIRouter()

_ENDPOINT = "/v1/responses"


@router.post("/responses")
async def responses(request: Request, key: HubKey = Depends(enforce_quotas)):
    body: dict[str, Any] = await request.json()
    model = str(body.get("model") or "")
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model is required.")
    if body.get("previous_response_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="previous_response_id is not supported; send the full conversation in `input`.",
        )
    if key.allowed_models and model not in key.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{model}' is not in this key's allowed_models whitelist.",
        )
    msgs, tools, options = responses_to_driver(body)

    from prompture.drivers import get_driver_for_model

    driver = get_driver_for_model(model)
    started = time.perf_counter()

    def record(outcome: ChatOutcome) -> None:
        usage = outcome.usage
        _record(
            key.id, model, usage["prompt_tokens"], usage["completion_tokens"], outcome.cost,
            int((time.perf_counter() - started) * 1000),
            "error" if outcome.error else "ok",
            str(outcome.error) if outcome.error else None,
            endpoint=_ENDPOINT,
            route=outcome.meta.get("route") or {"attempts": getattr(outcome.error, "attempts", None) or []},
        )

    if body.get("stream"):
        def event_gen() -> Iterator[str]:
            for event in stream_responses_events(
                live_events_for(driver, msgs, tools, options), model=model, on_complete=record,
            ):
                yield responses_sse(event)

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
    return response_object(outcome, model=model)

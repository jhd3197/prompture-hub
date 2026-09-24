"""OpenAI-compatible endpoints.

- ``POST /v1/chat/completions`` — drop-in chat completions routed through
  Prompture's driver registry. Supports ``tools``, multimodal ``image_url``
  parts and ``response_format``. ``stream: true`` returns an SSE stream of
  OpenAI chunks terminated by ``data: [DONE]``.
- ``GET  /v1/models`` — lists models the calling key is allowed to use.

Request/response shaping lives in :mod:`prompture.gateway`; this module only
adds the hub's concerns: key scoping, conversation replay/persistence and
metering.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from prompture.gateway import (
    SSE_DONE,
    SSE_HEADERS,
    ChatOutcome,
    driver_options,
    flatten_content,
    models_list,
    new_completion_id,
    run_chat,
    sse,
    stream_chat_chunks,
    to_driver_messages,
)
from pydantic import BaseModel, ConfigDict

from ..auth import require_hub_key
from ..quotas import enforce_quotas
from ..storage.db import get_session
from ..storage.models import Conversation, HubKey, UsageRecord
from .conversations import append_messages, load_history

router = APIRouter()

_ENDPOINT = "/v1/chat/completions"


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: Any = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatCompletionsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    top_p: float | None = None
    stop: Any = None
    seed: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    reasoning_effort: str | None = None
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    stream: bool = False
    stream_options: dict[str, Any] | None = None
    conversation_id: str | None = None
    persist: bool = True


def _gate_and_prepare(
    body: ChatCompletionsRequest, key: HubKey,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Shared pre-flight for streaming and non-streaming.

    Validates the model whitelist + conversation ownership, replays prior
    messages when ``conversation_id`` is set, and assembles driver options.
    """
    if key.allowed_models and body.model not in key.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{body.model}' is not in this key's allowed_models whitelist.",
        )

    history: list[dict[str, Any]] = []
    if body.conversation_id:
        with get_session() as session:
            conv = session.get(Conversation, body.conversation_id)
            if not conv or conv.key_id != key.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="conversation_id not found.",
                )
        history = load_history(body.conversation_id)

    messages = to_driver_messages(history + list(body.messages))
    options = driver_options(body)
    if body.tool_choice is not None:
        options["tool_choice"] = body.tool_choice
    return messages, options


def _persist(body: ChatCompletionsRequest, outcome: ChatOutcome) -> None:
    if not (body.conversation_id and body.persist):
        return
    usage = outcome.usage
    new_items: list[dict[str, Any]] = [
        {"role": m.role, "content": flatten_content(m.content)} for m in body.messages
    ]
    new_items.append(
        {
            "role": "assistant",
            "content": outcome.text,
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "cost_usd": outcome.cost,
        }
    )
    append_messages(body.conversation_id, new_items)


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionsRequest,
    key: HubKey = Depends(enforce_quotas),
):
    messages, options = _gate_and_prepare(body, key)

    from prompture.drivers import get_driver_for_model

    driver = get_driver_for_model(body.model)

    if body.stream:
        return _stream_response(driver, body, key, messages, options)

    started = time.perf_counter()
    try:
        outcome = await run_in_threadpool(run_chat, driver, messages, options, tools=body.tools)
    except NotImplementedError as exc:
        _record(key.id, body.model, 0, 0, 0.0, 0, "error", str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        # A resilient route that ran out of targets carries its attempt trace.
        route = {"attempts": getattr(exc, "attempts", None) or []}
        _record(key.id, body.model, 0, 0, 0.0, 0, "error", str(exc), route=route)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    usage = outcome.usage
    _record(
        key.id, body.model, usage["prompt_tokens"], usage["completion_tokens"],
        outcome.cost, int((time.perf_counter() - started) * 1000), "ok", None,
        route=outcome.meta.get("route"),
    )
    _persist(body, outcome)
    return outcome.to_completion(body.model, extra={"conversation_id": body.conversation_id})


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def _stream_response(
    driver: Any,
    body: ChatCompletionsRequest,
    key: HubKey,
    messages: list[dict[str, Any]],
    options: dict[str, Any],
) -> StreamingResponse:
    # Every Prompture driver inherits ``generate_messages_stream`` (it raises
    # NotImplementedError), so the capability flag is the real signal.
    can_stream = getattr(driver, "supports_streaming", None)
    if can_stream is None:
        can_stream = hasattr(driver, "generate_messages_stream")
    if not can_stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Driver for '{body.model}' does not support streaming. "
                "Retry with stream=false."
            ),
        )
    if body.tools:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Streaming with tools is not supported yet. Retry with stream=false.",
        )

    started = time.perf_counter()

    def on_complete(outcome: ChatOutcome) -> None:
        elapsed = int((time.perf_counter() - started) * 1000)
        usage = outcome.usage
        if outcome.error is not None:
            _record(
                key.id, body.model, usage["prompt_tokens"], usage["completion_tokens"],
                outcome.cost, elapsed, "error", str(outcome.error),
            )
            return
        _record(
            key.id, body.model, usage["prompt_tokens"], usage["completion_tokens"],
            outcome.cost, elapsed, "ok", None, route=outcome.meta.get("route"),
        )
        _persist(body, outcome)

    include_usage = bool((body.stream_options or {}).get("include_usage", True))

    def event_gen() -> Iterator[str]:
        chunks = stream_chat_chunks(
            driver.generate_messages_stream(messages, options),
            model=body.model,
            completion_id=new_completion_id(),
            include_usage=include_usage,
            on_complete=on_complete,
        )
        for chunk in chunks:
            yield sse(chunk)
        yield SSE_DONE

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# ---------------------------------------------------------------------------
# Models listing
# ---------------------------------------------------------------------------


@router.get("/models")
async def list_models(key: HubKey = Depends(require_hub_key)) -> dict[str, Any]:
    from prompture.infra.discovery import get_available_models
    from prompture.resilience import list_virtual_models

    all_names: list[str] = list_virtual_models() + list(get_available_models())
    if key.allowed_models:
        allowed = set(key.allowed_models)
        all_names = [n for n in all_names if n in allowed]
    return models_list(all_names, owned_by="prompture-hub")


def _record(
    key_id: int,
    model: str,
    prompt_tok: int,
    completion_tok: int,
    cost: float,
    elapsed_ms: int,
    status_str: str,
    error: str | None,
    endpoint: str = _ENDPOINT,
    route: dict[str, Any] | None = None,
) -> None:
    served_by = (route or {}).get("served_by")
    attempts = sum(1 for a in (route or {}).get("attempts", []) if a.get("outcome") in ("ok", "error"))
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
                served_by=served_by,
                attempts=max(attempts, 1),
            )
        )
        session.commit()

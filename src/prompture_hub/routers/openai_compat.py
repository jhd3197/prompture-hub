"""OpenAI-compatible endpoints.

- ``POST /v1/chat/completions`` — drop-in chat completions routed through
  Prompture's driver registry. Supports ``tools``, multimodal ``image_url``
  parts and ``response_format``. ``stream: true`` returns an SSE stream of
  OpenAI chunks terminated by ``data: [DONE]``.
- ``POST /v1/embeddings`` — Prompture's embedding drivers, metered per key.
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

from .. import metering
from ..auth import require_hub_key
from ..metering import request_project
from ..pipeline import after_turn, prepare_messages
from ..quotas import enforce_quotas
from ..storage.db import get_session
from ..storage.models import Conversation, HubKey
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

    messages = prepare_messages(to_driver_messages(history + list(body.messages)))
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
    project: str | None = Depends(request_project),
):
    messages, options = _gate_and_prepare(body, key)

    from prompture.drivers import get_driver_for_model

    routed = metering.effective_model(key, body.model)
    driver = get_driver_for_model(routed)

    if body.stream:
        return _stream_response(driver, body, key, messages, options, project)

    call = metering.begin(key, body.model, _ENDPOINT, project, routed_to=routed)
    started = time.perf_counter()
    try:
        outcome = await run_in_threadpool(run_chat, driver, messages, options, tools=body.tools)
    except NotImplementedError as exc:
        _record(key.id, body.model, 0, 0, 0.0, 0, "error", str(exc), project=project, call=call)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        # A resilient route that ran out of targets carries its attempt trace.
        route = {"attempts": getattr(exc, "attempts", None) or []}
        _record(key.id, body.model, 0, 0, 0.0, 0, "error", str(exc), route=route, project=project, call=call)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    after_turn(outcome)
    usage = outcome.usage
    _record(
        key.id, body.model, usage["prompt_tokens"], usage["completion_tokens"],
        outcome.cost, int((time.perf_counter() - started) * 1000), "ok", None,
        meta=outcome.meta, project=project, call=call,
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
    project: str | None = None,
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

    call = metering.begin(
        key, body.model, _ENDPOINT, project, stream=True, routed_to=metering.effective_model(key, body.model)
    )
    started = time.perf_counter()

    def on_complete(outcome: ChatOutcome) -> None:
        after_turn(outcome)
        elapsed = int((time.perf_counter() - started) * 1000)
        usage = outcome.usage
        if outcome.error is not None:
            _record(
                key.id, body.model, usage["prompt_tokens"], usage["completion_tokens"],
                outcome.cost, elapsed, "error", str(outcome.error), meta=outcome.meta, project=project, call=call,
            )
            return
        _record(
            key.id, body.model, usage["prompt_tokens"], usage["completion_tokens"],
            outcome.cost, elapsed, "ok", None, meta=outcome.meta, project=project, call=call,
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
        try:
            for chunk in chunks:
                call.mark_first_token()
                yield sse(chunk)
            yield SSE_DONE
        finally:
            call.close()

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


class EmbeddingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    input: str | list[str]
    encoding_format: str | None = None
    dimensions: int | None = None


@router.post("/embeddings")
async def embeddings(
    body: EmbeddingsRequest,
    key: HubKey = Depends(enforce_quotas),
    project: str | None = Depends(request_project),
) -> dict[str, Any]:
    if key.allowed_models and body.model not in key.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{body.model}' is not in this key's allowed_models whitelist.",
        )
    from prompture.drivers.embedding_registry import get_async_embedding_driver_for_model

    try:
        driver = get_async_embedding_driver_for_model(body.model)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown embedding model: {exc}") from exc

    inputs = body.input if isinstance(body.input, list) else [body.input]
    options: dict[str, Any] = {}
    if body.dimensions is not None:
        options["dimensions"] = body.dimensions

    call = metering.begin(key, body.model, "/v1/embeddings", project)
    started = time.perf_counter()
    try:
        result = await driver.embed(inputs, options)
    except Exception as exc:
        _record(
            key.id, body.model, 0, 0, 0.0, 0, "error", str(exc), endpoint="/v1/embeddings", project=project, call=call
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    meta = result.get("meta", {}) or {}
    tokens = int(meta.get("total_tokens", meta.get("prompt_tokens", 0)) or 0)
    _record(
        key.id, body.model, tokens, 0, float(meta.get("cost", 0.0) or 0.0),
        int((time.perf_counter() - started) * 1000), "ok", None, endpoint="/v1/embeddings", project=project,
        call=call,
    )
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": vec, "index": i} for i, vec in enumerate(result["embeddings"])],
        "model": meta.get("model_name", body.model),
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }


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
    *,
    meta: dict[str, Any] | None = None,
    project: str | None = None,
    call: metering.Call | None = None,
) -> None:
    """Meter one call. Pass the driver ``meta`` when there is one; ``route``
    alone covers failures that only carry an attempt trace."""
    if route is not None and not (meta or {}).get("route"):
        meta = {**(meta or {}), "route": route}
    metering.record(
        key_id=key_id,
        model=model,
        endpoint=endpoint,
        prompt_tokens=prompt_tok,
        completion_tokens=completion_tok,
        cost=cost,
        latency_ms=elapsed_ms,
        status=status_str,
        error=error,
        project=project,
        meta=meta,
        call=call,
    )

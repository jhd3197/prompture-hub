"""OpenAI-compatible endpoints.

- ``POST /v1/chat/completions`` — drop-in chat completions; routes to Prompture
  driver registry. Streaming (``stream: true``) returns an SSE event stream in
  OpenAI's chunk shape, terminated by ``data: [DONE]``.
- ``GET  /v1/models``           — lists models the calling key is allowed to use.

Non-streaming calls use ``driver.generate_messages`` when the driver supports
chat-shaped input and fall back to a flattened prompt otherwise. Blocking
driver calls run in a worker thread so they don't stall the event loop.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import require_hub_key
from ..quotas import enforce_quotas
from ..storage.db import get_session
from ..storage.models import Conversation, HubKey, UsageRecord
from .conversations import append_messages, load_history

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionsRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False
    conversation_id: str | None = None
    persist: bool = True


def _gate_and_prepare(
    body: ChatCompletionsRequest, key: HubKey,
) -> tuple[list[ChatMessage], dict[str, Any]]:
    """Shared pre-flight for streaming and non-streaming.

    Validates the model whitelist + conversation ownership, replays prior
    messages when ``conversation_id`` is set, and assembles driver options.
    """
    if key.allowed_models and body.model not in key.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{body.model}' is not in this key's allowed_models whitelist.",
        )

    if body.conversation_id:
        with get_session() as session:
            conv = session.get(Conversation, body.conversation_id)
            if not conv or conv.key_id != key.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="conversation_id not found.",
                )
        prior = load_history(body.conversation_id)
        history = [ChatMessage(role=p["role"], content=p["content"]) for p in prior]
        full_messages = history + list(body.messages)
    else:
        full_messages = list(body.messages)

    options: dict[str, Any] = {}
    if body.temperature is not None:
        options["temperature"] = body.temperature
    if body.max_tokens is not None:
        options["max_tokens"] = body.max_tokens
    if body.top_p is not None:
        options["top_p"] = body.top_p

    return full_messages, options


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionsRequest,
    key: HubKey = Depends(enforce_quotas),
):
    full_messages, options = _gate_and_prepare(body, key)

    from prompture.drivers import get_driver_for_model

    driver = get_driver_for_model(body.model)

    if body.stream:
        return _stream_response(driver, body, key, full_messages, options)

    started = time.perf_counter()
    try:
        result = await run_in_threadpool(_generate, driver, full_messages, options)
    except Exception as exc:
        _record(key.id, body.model, "/v1/chat/completions", 0, 0, 0.0, 0, "error", str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    text = result.get("text", "")
    # Drivers report usage under ``meta``; ``usage`` is accepted for stubs and
    # older wrappers that already speak the OpenAI shape.
    usage = result.get("meta") or result.get("usage") or {}
    prompt_tok = int(usage.get("prompt_tokens", 0) or 0)
    completion_tok = int(usage.get("completion_tokens", 0) or 0)
    total_tok = int(usage.get("total_tokens", 0) or (prompt_tok + completion_tok))
    cost = float(usage.get("cost", 0.0) or 0.0)

    _record(
        key.id, body.model, "/v1/chat/completions",
        prompt_tok, completion_tok, cost, elapsed_ms, "ok", None,
    )

    if body.conversation_id and body.persist:
        new_items: list[dict[str, Any]] = [
            {"role": m.role, "content": m.content} for m in body.messages
        ]
        new_items.append(
            {
                "role": "assistant",
                "content": text,
                "prompt_tokens": prompt_tok,
                "completion_tokens": completion_tok,
                "total_tokens": total_tok,
                "cost_usd": cost,
            }
        )
        append_messages(body.conversation_id, new_items)

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tok,
            "completion_tokens": completion_tok,
            "total_tokens": total_tok,
        },
        "conversation_id": body.conversation_id,
    }


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def _sse(payload: dict[str, Any] | str) -> str:
    """Format an SSE line. Strings (e.g. ``[DONE]``) are passed through."""
    if isinstance(payload, str):
        return f"data: {payload}\n\n"
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _chunk(stream_id: str, model: str, delta: dict[str, Any], finish: str | None) -> dict[str, Any]:
    return {
        "id": stream_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _stream_response(
    driver: Any,
    body: ChatCompletionsRequest,
    key: HubKey,
    full_messages: list[ChatMessage],
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

    stream_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    msgs_for_driver = [{"role": m.role, "content": m.content} for m in full_messages]

    def event_gen() -> Iterator[str]:
        started = time.perf_counter()
        full_text = ""
        prompt_tok = 0
        completion_tok = 0
        cost = 0.0

        # Role chunk first — matches OpenAI's protocol so SDKs initialize cleanly.
        yield _sse(_chunk(stream_id, body.model, {"role": "assistant"}, None))

        try:
            for event in driver.generate_messages_stream(msgs_for_driver, options):
                kind = event.get("type")
                if kind == "delta":
                    text = event.get("text", "")
                    if text:
                        full_text += text
                        yield _sse(_chunk(stream_id, body.model, {"content": text}, None))
                elif kind == "done":
                    meta = event.get("meta", {}) or {}
                    full_text = event.get("text", full_text) or full_text
                    prompt_tok = int(meta.get("prompt_tokens", 0))
                    completion_tok = int(meta.get("completion_tokens", 0))
                    cost = float(meta.get("cost", 0.0))
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            _record(
                key.id, body.model, "/v1/chat/completions",
                prompt_tok, completion_tok, cost, elapsed, "error", str(exc),
            )
            # OpenAI clients tolerate an "error" data event followed by [DONE].
            yield _sse({"error": {"message": str(exc), "type": "driver_error"}})
            yield _sse("[DONE]")
            return

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        # Final delta with finish_reason=stop, then [DONE].
        yield _sse(_chunk(stream_id, body.model, {}, "stop"))
        yield _sse("[DONE]")

        _record(
            key.id, body.model, "/v1/chat/completions",
            prompt_tok, completion_tok, cost, elapsed_ms, "ok", None,
        )

        if body.conversation_id and body.persist:
            new_items: list[dict[str, Any]] = [
                {"role": m.role, "content": m.content} for m in body.messages
            ]
            new_items.append(
                {
                    "role": "assistant",
                    "content": full_text,
                    "prompt_tokens": prompt_tok,
                    "completion_tokens": completion_tok,
                    "total_tokens": prompt_tok + completion_tok,
                    "cost_usd": cost,
                }
            )
            append_messages(body.conversation_id, new_items)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Models listing
# ---------------------------------------------------------------------------


@router.get("/models")
async def list_models(key: HubKey = Depends(require_hub_key)) -> dict[str, Any]:
    from prompture.infra.discovery import get_available_models

    all_names: list[str] = list(get_available_models())
    if key.allowed_models:
        allowed = set(key.allowed_models)
        all_names = [n for n in all_names if n in allowed]
    return {
        "object": "list",
        "data": [{"id": n, "object": "model", "owned_by": "prompture-hub"} for n in all_names],
    }


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    return "\n\n".join(f"{m.role}: {m.content}" for m in messages)


def _generate(driver: Any, messages: list[ChatMessage], options: dict[str, Any]) -> dict[str, Any]:
    """Call the driver with chat-shaped input when it supports it."""
    if getattr(driver, "supports_messages", False):
        return driver.generate_messages(
            [{"role": m.role, "content": m.content} for m in messages], options
        )
    return driver.generate(_messages_to_prompt(messages), options)


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

"""OpenAI-compatible endpoints.

- ``POST /v1/chat/completions`` — drop-in chat completions; routes to Prompture driver registry.
- ``GET  /v1/models``           — lists models the calling key is allowed to use.

v0.1 limitations (planned for v0.2):
- No streaming (``stream: true`` returns 501).
- ``messages`` are flattened to a single prompt string for ``driver.generate()``;
  per-provider chat templating is left to the driver. Most Prompture drivers DTRT.
- No ``/v1/embeddings`` yet.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionsRequest,
    key: HubKey = Depends(enforce_quotas),
) -> dict[str, Any]:
    if body.stream:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Streaming not implemented in v0.1; planned for v0.2.",
        )
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
        history: list[ChatMessage] = [
            ChatMessage(role=p["role"], content=p["content"]) for p in prior
        ]
        full_messages = history + list(body.messages)
    else:
        full_messages = list(body.messages)

    from prompture.drivers import get_driver_for_model

    driver = get_driver_for_model(body.model)
    prompt = _messages_to_prompt(full_messages)

    options: dict[str, Any] = {}
    if body.temperature is not None:
        options["temperature"] = body.temperature
    if body.max_tokens is not None:
        options["max_tokens"] = body.max_tokens
    if body.top_p is not None:
        options["top_p"] = body.top_p

    started = time.perf_counter()
    try:
        result = driver.generate(prompt, options)
    except Exception as exc:
        _record(key.id, body.model, "/v1/chat/completions", 0, 0, 0.0, 0, "error", str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    text = result.get("text", "")
    usage = result.get("usage", {}) or {}
    prompt_tok = int(usage.get("prompt_tokens", 0))
    completion_tok = int(usage.get("completion_tokens", 0))
    total_tok = int(usage.get("total_tokens", prompt_tok + completion_tok))
    cost = float(usage.get("cost", 0.0))

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

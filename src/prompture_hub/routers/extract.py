"""Prompture-native structured extraction over HTTP.

``POST /v1/extract`` — accept ``content`` + ``json_schema`` (+ optional model, strategy,
system_prompt, options), call :func:`prompture.extraction.core.ask_for_json`, return the
parsed object plus usage metadata.

This is the surface that justifies running prompture-hub over a plain OpenAI proxy:
clients get Prompture's schema-first extraction with strategy selection
(``provider_native`` / ``tool_call`` / ``prompted_repair``) without bundling Prompture
into their own runtime.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from ..quotas import enforce_quotas
from ..storage.db import get_session
from ..storage.models import HubKey, UsageRecord

router = APIRouter()


class ExtractRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    content: str = Field(description="Source text / prompt content to extract from.")
    json_schema: dict[str, Any] = Field(description="JSON Schema describing the target object.")
    model: str = Field(description="provider/model identifier, e.g. 'ollama/llama3.1:8b'.")
    system_prompt: str | None = Field(default=None, description="Optional system-role override.")
    strategy: str | None = Field(
        default=None,
        description="StructuredOutputStrategy: 'provider_native' | 'tool_call' | 'prompted_repair'. None = auto.",
    )
    options: dict[str, Any] | None = Field(default=None, description="Extra driver options.")


@router.post("/extract")
async def extract(
    body: ExtractRequest,
    key: HubKey = Depends(enforce_quotas),
) -> dict[str, Any]:
    if key.allowed_models and body.model not in key.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{body.model}' is not in this key's allowed_models whitelist.",
        )

    from prompture.drivers import get_driver_for_model
    from prompture.extraction.core import ask_for_json

    driver = get_driver_for_model(body.model)
    started = time.perf_counter()
    try:
        result = await run_in_threadpool(
            ask_for_json,
            driver=driver,
            content_prompt=body.content,
            json_schema=body.json_schema,
            model_name=body.model,
            options=body.options,
            system_prompt=body.system_prompt,
            strategy=body.strategy,
        )
    except Exception as exc:
        with get_session() as session:
            session.add(
                UsageRecord(
                    key_id=key.id,
                    model=body.model,
                    endpoint="/v1/extract",
                    status="error",
                    error=str(exc),
                )
            )
            session.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    usage = result.get("usage", {}) or {}
    prompt_tok = int(usage.get("prompt_tokens", 0))
    completion_tok = int(usage.get("completion_tokens", 0))
    cost = float(usage.get("cost", 0.0))

    with get_session() as session:
        session.add(
            UsageRecord(
                key_id=key.id,
                model=body.model,
                endpoint="/v1/extract",
                prompt_tokens=prompt_tok,
                completion_tokens=completion_tok,
                total_tokens=prompt_tok + completion_tok,
                cost_usd=cost,
                latency_ms=elapsed_ms,
                status="ok",
            )
        )
        session.commit()

    return {
        "data": result.get("json_object"),
        "usage": {
            "prompt_tokens": prompt_tok,
            "completion_tokens": completion_tok,
            "total_tokens": prompt_tok + completion_tok,
            "cost_usd": cost,
            "latency_ms": elapsed_ms,
            "strategy": usage.get("strategy"),
        },
    }

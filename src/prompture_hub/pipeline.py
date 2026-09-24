"""Request/response hooks shared by every chat-style endpoint.

- :func:`prepare_messages` runs before the driver call: re-attaches cached
  reasoning for thinking models, then applies ``HUB_COMPRESSION``.
- :func:`after_turn` runs once a turn finishes: remembers new reasoning.
"""

from __future__ import annotations

from typing import Any

from prompture.gateway import ChatOutcome, get_reasoning_cache

from .settings import get_settings


def prepare_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages = get_reasoning_cache().restore(messages)
    if get_settings().compression == "lite":
        from prompture.infra.compression import compress_messages

        messages, _stats = compress_messages(messages)
    return messages


def after_turn(outcome: ChatOutcome) -> None:
    if outcome.error is None:
        get_reasoning_cache().remember(outcome)

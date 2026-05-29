"""Conversation persistence — resumable chat sessions.

A conversation is owned by the HubKey that created it. Each turn appended
via ``/v1/chat/completions`` (with ``conversation_id`` set) is persisted as
a :class:`Message`, so a later request can resume the session by replaying
its history.

Endpoints
---------
- ``POST   /v1/conversations``              create
- ``GET    /v1/conversations``              list (caller's only)
- ``GET    /v1/conversations/{id}``         fetch with messages
- ``DELETE /v1/conversations/{id}``         delete (cascades messages)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from ..auth import require_hub_key
from ..storage.db import get_session
from ..storage.models import Conversation, HubKey, Message, iso_utc

router = APIRouter()


class CreateConversationRequest(BaseModel):
    title: str | None = None
    model: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    system: str | None = Field(
        default=None,
        description="Optional system prompt persisted as the first message.",
    )


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    model: str | None
    created_at: str
    updated_at: str
    message_count: int


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    tool_calls: list | None = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    created_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str | None
    model: str | None
    meta: dict[str, Any]
    created_at: str
    updated_at: str
    messages: list[MessageOut]


def _require_owned_conversation(conv_id: str, key: HubKey) -> Conversation:
    with get_session() as session:
        conv = session.get(Conversation, conv_id)
        if not conv or conv.key_id != key.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )
        return conv


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    body: CreateConversationRequest,
    key: HubKey = Depends(require_hub_key),
) -> ConversationSummary:
    with get_session() as session:
        conv = Conversation(
            key_id=key.id,
            title=body.title,
            model=body.model,
            meta=body.meta,
        )
        session.add(conv)
        session.commit()
        session.refresh(conv)
        msg_count = 0
        if body.system:
            session.add(
                Message(
                    conversation_id=conv.id,
                    role="system",
                    content=body.system,
                )
            )
            session.commit()
            msg_count = 1
        return ConversationSummary(
            id=conv.id,
            title=conv.title,
            model=conv.model,
            created_at=iso_utc(conv.created_at),
            updated_at=iso_utc(conv.updated_at),
            message_count=msg_count,
        )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    limit: int = 50,
    key: HubKey = Depends(require_hub_key),
) -> list[ConversationSummary]:
    with get_session() as session:
        stmt = (
            select(Conversation)
            .where(Conversation.key_id == key.id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        convs = session.exec(stmt).all()
        out: list[ConversationSummary] = []
        for c in convs:
            count = len(
                session.exec(
                    select(Message.id).where(Message.conversation_id == c.id)
                ).all()
            )
            out.append(
                ConversationSummary(
                    id=c.id,
                    title=c.title,
                    model=c.model,
                    created_at=iso_utc(c.created_at),
                    updated_at=iso_utc(c.updated_at),
                    message_count=count,
                )
            )
        return out


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(
    conv_id: str,
    key: HubKey = Depends(require_hub_key),
) -> ConversationDetail:
    _require_owned_conversation(conv_id, key)
    with get_session() as session:
        conv = session.get(Conversation, conv_id)
        msgs = session.exec(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
        ).all()
        return ConversationDetail(
            id=conv.id,
            title=conv.title,
            model=conv.model,
            meta=conv.meta or {},
            created_at=iso_utc(conv.created_at),
            updated_at=iso_utc(conv.updated_at),
            messages=[
                MessageOut(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    tool_calls=m.tool_calls,
                    prompt_tokens=m.prompt_tokens,
                    completion_tokens=m.completion_tokens,
                    total_tokens=m.total_tokens,
                    cost_usd=m.cost_usd,
                    created_at=iso_utc(m.created_at),
                )
                for m in msgs
            ],
        )


@router.delete(
    "/conversations/{conv_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conv_id: str,
    key: HubKey = Depends(require_hub_key),
) -> Response:
    _require_owned_conversation(conv_id, key)
    with get_session() as session:
        for m in session.exec(
            select(Message).where(Message.conversation_id == conv_id)
        ).all():
            session.delete(m)
        session.delete(session.get(Conversation, conv_id))
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def load_history(conv_id: str) -> list[dict[str, Any]]:
    """Return ordered ``[{role, content}, ...]`` for the conversation.

    Used by /v1/chat/completions to replay state before invoking the driver.
    Caller is responsible for ownership checks.
    """
    with get_session() as session:
        msgs = session.exec(
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at.asc())
        ).all()
        return [{"role": m.role, "content": m.content} for m in msgs]


def append_messages(
    conv_id: str,
    items: list[dict[str, Any]],
) -> None:
    """Append messages to a conversation and bump its ``updated_at``."""
    if not items:
        return
    with get_session() as session:
        for item in items:
            session.add(
                Message(
                    conversation_id=conv_id,
                    role=item["role"],
                    content=item.get("content", ""),
                    tool_calls=item.get("tool_calls"),
                    prompt_tokens=int(item.get("prompt_tokens", 0)),
                    completion_tokens=int(item.get("completion_tokens", 0)),
                    total_tokens=int(item.get("total_tokens", 0)),
                    cost_usd=float(item.get("cost_usd", 0.0)),
                )
            )
        conv = session.get(Conversation, conv_id)
        if conv:
            conv.updated_at = datetime.now(timezone.utc)
            session.add(conv)
        session.commit()

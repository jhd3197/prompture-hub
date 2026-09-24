"""SQLModel tables backing prompture-hub.

- :class:`HubKey` — one scoped credential issued to an untrusted app.
- :class:`UsageRecord` — one row per /v1/* call; powers the dashboard and quotas.
- :class:`Conversation` — a resumable chat session owned by a HubKey.
- :class:`Message` — one turn within a Conversation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None) -> str | None:
    """Serialize a datetime as UTC ISO-8601 with an explicit offset.

    SQLite does not preserve tzinfo, so datetimes read back from the DB are
    naive even though we always store UTC. A bare ``.isoformat()`` on a naive
    value emits no offset, which browsers (and any client) parse as *local*
    time — shifting timestamps by the viewer's UTC offset. Assume UTC when
    tzinfo is missing, then emit with ``+00:00`` so the value is unambiguous.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class HubKey(SQLModel, table=True):
    """A hub-issued scoped key. Plaintext shown once; only hash is stored."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="Human label, e.g. 'sketchy-app-1'.")
    hashed_secret: str = Field(unique=True, index=True)
    allowed_models: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    daily_spend_cap_usd: float = Field(
        default=1.0,
        description=(
            "Cap value; the period it applies over is given by ``spend_period``. "
            "Name kept for backwards compatibility with the v0 schema."
        ),
    )
    spend_period: str = Field(
        default="day",
        description="day | week | month — UTC-anchored window the cap resets on.",
    )
    rate_limit_per_min: int = Field(default=60)
    allowed_ips: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="IPs / CIDR ranges allowed to use the key. Empty = any.",
    )
    expires_at: datetime | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    revoked_at: datetime | None = Field(default=None, index=True)
    user_id: int | None = Field(default=None, index=True, foreign_key="user.id")
    default_project: str | None = Field(
        default=None,
        description="Project a call is attributed to when the request sends no X-Project header.",
    )


class UsageRecord(SQLModel, table=True):
    """One row per /v1/* call."""

    id: int | None = Field(default=None, primary_key=True)
    key_id: int = Field(index=True, foreign_key="hubkey.id")
    model: str = Field(index=True)
    endpoint: str = Field(description="e.g. /v1/chat/completions, /v1/extract")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    latency_ms: int = Field(default=0)
    status: str = Field(
        default="ok",
        description="ok | error | quota_exceeded | rate_limited",
    )
    error: str | None = Field(default=None)
    served_by: str | None = Field(
        default=None,
        description="Model that actually answered (differs from ``model`` for combos / fallbacks).",
    )
    attempts: int = Field(default=1, description="Upstream attempts, including retries and fallbacks.")
    project: str | None = Field(default=None, index=True, description="Project label (X-Project header or key default).")
    timestamp: datetime = Field(default_factory=_utcnow, index=True)


class User(SQLModel, table=True):
    """A dashboard user authenticated via OAuth (Google or GitHub).

    Allowlist enforcement is in the auth router — presence in this table only
    means the user successfully completed the OAuth dance at least once.
    """

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str | None = Field(default=None)
    avatar_url: str | None = Field(default=None)
    provider: str = Field(description="google | github")
    provider_user_id: str = Field(index=True)
    is_admin: bool = Field(default=True, description="Solo-mode: every allowlisted user is admin.")
    created_at: datetime = Field(default_factory=_utcnow)
    last_login_at: datetime = Field(default_factory=_utcnow)


def _new_conv_id() -> str:
    return f"conv_{uuid.uuid4().hex[:24]}"


def _new_msg_id() -> str:
    return f"msg_{uuid.uuid4().hex[:24]}"


class Conversation(SQLModel, table=True):
    """A resumable chat session. Messages are replayed on each turn so the
    LLM call stays stateless on the provider side."""

    id: str = Field(default_factory=_new_conv_id, primary_key=True)
    key_id: int = Field(index=True, foreign_key="hubkey.id")
    title: str | None = Field(default=None)
    model: str | None = Field(
        default=None,
        description="Default model for this conversation; overridable per turn.",
    )
    meta: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    updated_at: datetime = Field(default_factory=_utcnow, index=True)


class Message(SQLModel, table=True):
    """One turn within a Conversation. Stored verbatim so resumed sessions
    can be replayed losslessly."""

    id: str = Field(default_factory=_new_msg_id, primary_key=True)
    conversation_id: str = Field(index=True, foreign_key="conversation.id")
    role: str = Field(description="system | user | assistant | tool")
    content: str = Field(default="")
    tool_calls: list | None = Field(default=None, sa_column=Column(JSON))
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    cost_usd: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=_utcnow, index=True)


class DeviceToken(SQLModel, table=True):
    """A credential for a desktop companion (or any read-mostly client).

    Minted through device pairing, never shown in the dashboard. ``scopes``
    is ``["read"]`` or ``["read", "control"]``; control is granted separately
    because it can change keys and routes.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(description="Label chosen when the device was approved.")
    hashed_secret: str = Field(unique=True, index=True)
    scopes: list[str] = Field(default_factory=lambda: ["read"], sa_column=Column(JSON))
    user_id: int | None = Field(default=None, index=True, foreign_key="user.id")
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None, index=True)


class DevicePairing(SQLModel, table=True):
    """One pending device authorization (RFC 8628 device code + user code)."""

    id: int | None = Field(default=None, primary_key=True)
    device_code_hash: str = Field(unique=True, index=True)
    user_code: str = Field(unique=True, index=True)
    client_name: str | None = Field(default=None)
    requested_scopes: list[str] = Field(default_factory=lambda: ["read"], sa_column=Column(JSON))
    status: str = Field(default="pending", description="pending | approved | denied | consumed")
    approved_name: str | None = Field(default=None)
    approved_scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    approved_by: int | None = Field(default=None, foreign_key="user.id")
    token_id: int | None = Field(default=None, foreign_key="devicetoken.id")
    interval: int = Field(default=5)
    last_poll_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime = Field(index=True)


class AlertRule(SQLModel, table=True):
    """A condition worth telling someone about, and where to tell them.

    ``kind`` decides what ``threshold`` means:

    - ``key_spend`` — fraction (0-1) of a key's spend cap used this period.
    - ``provider_headroom`` — fraction of a provider rate-limit window left.
    - ``balance_low`` — provider account balance below this amount.
    - ``fallback`` / ``error`` — no threshold; any fallback / failed call.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    kind: str = Field(index=True)
    threshold: float | None = Field(default=None)
    key_id: int | None = Field(default=None, foreign_key="hubkey.id", description="Only this key (key rules).")
    target: str | None = Field(default=None, description="Only this model / account source.")
    webhook_url: str | None = Field(default=None)
    ntfy_url: str | None = Field(default=None, description="ntfy topic URL, e.g. https://ntfy.sh/my-topic")
    cooldown_minutes: int = Field(default=60, description="Minimum gap between repeats of the same alert.")
    enabled: bool = Field(default=True, index=True)
    user_id: int | None = Field(default=None, index=True, foreign_key="user.id")
    created_at: datetime = Field(default_factory=_utcnow)


class AlertEvent(SQLModel, table=True):
    """One time an alert rule fired."""

    id: int | None = Field(default=None, primary_key=True)
    rule_id: int = Field(index=True, foreign_key="alertrule.id")
    kind: str
    subject: str = Field(index=True, description="What the alert is about, e.g. 'key:3' or 'openai/gpt-4o'.")
    message: str
    value: float | None = Field(default=None)
    key_id: int | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
    acknowledged_at: datetime | None = Field(default=None)

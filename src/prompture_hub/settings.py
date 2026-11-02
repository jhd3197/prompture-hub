"""Hub configuration via pydantic-settings.

Loads from environment / `.env` with `HUB_` prefix. Real provider keys
(OPENAI_API_KEY etc.) are NOT defined here — Prompture's drivers read those
directly from environment, so they never need to pass through this layer.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HubSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HUB_",
        extra="ignore",
        case_sensitive=False,
    )

    admin_token: str = Field(
        default="",
        description="Bearer token gating /admin/*. If empty, admin endpoints return 503.",
    )
    db_path: str = Field(default="./prompture_hub.db")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=1984)

    base_url: str = Field(
        default="http://localhost:1984",
        description="Public base URL of this hub; used to build OAuth callback URLs.",
    )
    session_secret: str = Field(
        default="",
        description="Secret used to sign session cookies. If empty, dashboard login is disabled.",
    )
    session_cookie_name: str = Field(default="hub_session")
    session_max_age: int = Field(default=60 * 60 * 24 * 14, description="Seconds.")
    allowed_emails: str = Field(
        default="",
        description="Comma-separated email allowlist for dashboard login. Empty = no logins allowed.",
    )

    compression: str = Field(
        default="off",
        description=(
            "off | lite. lite trims older oversized tool results and duplicate "
            "system prompts before calling the model (see prompture.infra.compression)."
        ),
    )
    trust_proxy_headers: bool = Field(
        default=False,
        description=(
            "Trust X-Forwarded-For for the caller's IP (key IP allowlists). "
            "Only enable when the hub sits behind a proxy you control."
        ),
    )

    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")

    github_client_id: str = Field(default="")
    github_client_secret: str = Field(default="")

    disabled_providers: str = Field(
        default="cachibot",
        description=(
            "Comma-separated provider names to hide from /api/models. "
            "Use to suppress internal routers / unfinished drivers without "
            "touching Prompture itself. Case-insensitive."
        ),
    )

    @property
    def disabled_provider_set(self) -> set[str]:
        return {
            p.strip().lower()
            for p in self.disabled_providers.split(",")
            if p.strip()
        }

    # --- coding agent execution ---
    agent_workspace: str = Field(
        default="./agent-workspace",
        description=(
            "Directory under which coding-agent runs must execute. Requests "
            "specifying a cwd outside this tree are refused. Created on demand."
        ),
    )
    allow_agent_yolo: bool = Field(
        default=False,
        description=(
            "When False, /v1/coding-agents/run rejects approval_mode='yolo'. "
            "Set true only if you accept that the agent can do anything inside "
            "the workspace without prompting."
        ),
    )
    agent_default_timeout: int = Field(
        default=600,
        description="Per-run subprocess timeout in seconds.",
    )

    # --- spend-cap enforcement ---
    unknown_pricing: Literal["block", "warn"] = Field(
        default="block",
        description=(
            "block | warn. What to do with a call whose model has no known token "
            "prices (spend can't be metered): refuse it with 402, or allow it with "
            "an X-Hub-Cost-Warning header and no cost reservation."
        ),
    )
    default_output_token_estimate: int = Field(
        default=1024,
        ge=0,
        description="Output tokens assumed when reserving cost for a call that sets no max_tokens.",
    )
    reservation_ttl_seconds: float = Field(
        default=900,
        gt=0,
        description="Safety net: an in-flight cost reservation that was never released expires after this long.",
    )

    @field_validator("unknown_pricing", mode="before")
    @classmethod
    def _normalize_unknown_pricing(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @property
    def allowed_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.session_secret) and (self.google_enabled or self.github_enabled)


@lru_cache(maxsize=1)
def get_settings() -> HubSettings:
    return HubSettings()

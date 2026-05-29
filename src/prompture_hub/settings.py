"""Hub configuration via pydantic-settings.

Loads from environment / `.env` with `HUB_` prefix. Real provider keys
(OPENAI_API_KEY etc.) are NOT defined here — Prompture's drivers read those
directly from environment, so they never need to pass through this layer.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
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

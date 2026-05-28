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


@lru_cache(maxsize=1)
def get_settings() -> HubSettings:
    return HubSettings()

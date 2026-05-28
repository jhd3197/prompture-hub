"""Authlib OAuth client registration for Google + GitHub.

Lazy-built: the OAuth registry is constructed on first access so settings
changes during tests can take effect. If a provider's client id/secret is
missing, it simply isn't registered — the auth router checks this and
returns a friendly 503 for that provider.
"""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from .settings import get_settings

_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    global _oauth
    if _oauth is not None:
        return _oauth

    s = get_settings()
    oauth = OAuth()

    if s.google_enabled:
        oauth.register(
            name="google",
            client_id=s.google_client_id,
            client_secret=s.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    if s.github_enabled:
        oauth.register(
            name="github",
            client_id=s.github_client_id,
            client_secret=s.github_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )

    _oauth = oauth
    return oauth


def reset_oauth() -> None:
    """Test hook — drop the cached OAuth instance so settings can be rebuilt."""
    global _oauth
    _oauth = None

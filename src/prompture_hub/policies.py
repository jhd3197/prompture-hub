"""Per-key access policies: client IP allowlists and expiry.

Kept separate from :mod:`.quotas` (spend + rate) because these are
*identity* checks — they decide whether the key may be used at all, before
any metering happens.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

from .settings import get_settings
from .storage.models import HubKey


def normalize_ip_rules(rules: list[str] | None) -> list[str]:
    """Validate and canonicalize IPs / CIDR ranges. Raises 400 on a bad entry."""
    out: list[str] = []
    for raw in rules or []:
        rule = raw.strip()
        if not rule:
            continue
        try:
            net = ipaddress.ip_network(rule, strict=False)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid IP or CIDR range: {rule!r}",
            ) from exc
        canonical = str(net)
        if canonical not in out:
            out.append(canonical)
    return out


def ip_allowed(ip: str | None, rules: list[str] | None) -> bool:
    if not rules:
        return True
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in ipaddress.ip_network(rule, strict=False) for rule in rules)


def client_ip(request: Request) -> str | None:
    """Caller's IP. ``X-Forwarded-For`` is only trusted when
    ``HUB_TRUST_PROXY_HEADERS=true`` (i.e. the hub sits behind your own proxy)."""
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def resolve_expiry(expires_at: datetime | None, expires_in_days: int | None) -> datetime | None:
    if expires_at is not None and expires_in_days is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass either expires_at or expires_in_days, not both.",
        )
    if expires_in_days is not None:
        if expires_in_days <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expires_in_days must be positive.",
            )
        return datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    if expires_at is not None and expires_at.tzinfo is None:
        return expires_at.replace(tzinfo=timezone.utc)
    return expires_at


def is_expired(key: HubKey, now: datetime | None = None) -> bool:
    if key.expires_at is None:
        return False
    exp = key.expires_at if key.expires_at.tzinfo else key.expires_at.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) >= exp


def enforce_key_policies(key: HubKey, request: Request) -> None:
    if is_expired(key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hub key has expired.",
        )
    if not ip_allowed(client_ip(request), key.allowed_ips or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This hub key is not allowed from your IP address.",
        )

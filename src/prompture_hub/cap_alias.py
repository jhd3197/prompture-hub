"""Deprecated ``daily_spend_cap_usd`` alias for ``spend_cap_usd`` (request bodies, responses, headers)."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from fastapi import Response
from pydantic import BaseModel, Field, model_validator

log = logging.getLogger(__name__)
OLD = "daily_spend_cap_usd"
_warned = False


class CapAliasBody(BaseModel):
    """Request-body base accepting both names; after validation ``spend_cap_usd`` holds the value."""

    spend_cap_usd: float | None = Field(default=None, ge=0)
    daily_spend_cap_usd: float | None = Field(default=None, ge=0, description="Deprecated alias of spend_cap_usd.")
    _cap_nullable: ClassVar[bool] = True

    @model_validator(mode="after")
    def _merge_cap(self) -> CapAliasBody:
        fs = self.model_fields_set
        new, old = "spend_cap_usd" in fs, OLD in fs
        if new and old and self.spend_cap_usd != self.daily_spend_cap_usd:
            raise ValueError(f"spend_cap_usd and {OLD} (deprecated alias) disagree; send only spend_cap_usd.")
        sent = self.spend_cap_usd if new else self.daily_spend_cap_usd
        if (new or old) and sent is None and not self._cap_nullable:
            raise ValueError("spend_cap_usd cannot be null.")
        if old and not new:
            self.spend_cap_usd = self.daily_spend_cap_usd
        return self

    def cap_or(self, default: float) -> float:
        return default if self.spend_cap_usd is None else self.spend_cap_usd

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude={OLD})


def flag_deprecated(body: CapAliasBody, response: Response) -> None:
    """Add Deprecation/Warning headers (and log once per process) when the old name was sent."""
    global _warned
    if OLD not in body.model_fields_set:
        return
    response.headers["Deprecation"] = "true"
    response.headers["Warning"] = '299 - "daily_spend_cap_usd is deprecated; use spend_cap_usd"'
    if not _warned:
        _warned = True
        log.warning("daily_spend_cap_usd is deprecated; use spend_cap_usd")


def cap_fields(value: float) -> dict[str, float]:
    """Both names, same value, for responses."""
    return {"spend_cap_usd": value, OLD: value}


def with_old_name(changes: dict[str, Any]) -> dict[str, Any]:
    """Event payload ``changes`` that still carries the old name for older listeners."""
    return {**changes, OLD: changes["spend_cap_usd"]} if "spend_cap_usd" in changes else changes

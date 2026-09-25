"""Alert rules: evaluate after each metered call, notify through channels.

Rules live in :class:`~.storage.models.AlertRule`. :func:`evaluate_call`
runs after every usage row is written; :func:`evaluate_accounts` runs when
account balances are fetched. A rule that matches *fires*: it writes an
:class:`~.storage.models.AlertEvent`, publishes ``alert.fired`` on the live
stream, and posts to the rule's webhook / ntfy topic in the background.

A rule fires at most once per ``cooldown_minutes`` for the same subject, so
a key sitting above its threshold produces a reminder per cooldown rather
than one alert per call.

Default thresholds come from Prompture itself: spend alerts use the budget
module's degrade threshold and headroom alerts use the resilience layer's
``RetryPolicy.min_headroom``, so "nearly out" means the same thing to the
router and to the person being alerted.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlmodel import select

from . import live
from .storage.db import get_session
from .storage.models import AlertEvent, AlertRule, HubKey, UsageRecord, iso_utc

logger = logging.getLogger("prompture_hub.alerts")

KINDS = ("key_spend", "provider_headroom", "balance_low", "fallback", "error")

_notify_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hub-alert")


def default_threshold(kind: str) -> float | None:
    if kind == "key_spend":
        try:
            from prompture.infra.budget import _DEGRADE_THRESHOLD

            return float(_DEGRADE_THRESHOLD)
        except (ImportError, AttributeError):
            return 0.8
    if kind == "provider_headroom":
        try:
            from prompture.resilience import RetryPolicy

            value = RetryPolicy().min_headroom
            return float(value) if value is not None else 0.05
        except (ImportError, AttributeError):
            return 0.05
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled_rules(kinds: tuple[str, ...]) -> list[AlertRule]:
    with get_session() as session:
        return list(
            session.exec(select(AlertRule).where(AlertRule.enabled.is_(True), AlertRule.kind.in_(kinds))).all()
        )


def _in_cooldown(session: Any, rule: AlertRule, subject: str) -> bool:
    since = _now() - timedelta(minutes=max(rule.cooldown_minutes, 0))
    return (
        session.exec(
            select(AlertEvent.id).where(
                AlertEvent.rule_id == rule.id,
                AlertEvent.subject == subject,
                AlertEvent.created_at >= since,
            )
        ).first()
        is not None
    )


def fire(rule: AlertRule, subject: str, message: str, *, value: float | None = None, key_id: int | None = None):
    """Record and deliver one alert unless the rule is cooling down for *subject*."""
    with get_session() as session:
        if _in_cooldown(session, rule, subject):
            return None
        event = AlertEvent(rule_id=rule.id, kind=rule.kind, subject=subject, message=message, value=value, key_id=key_id)
        session.add(event)
        session.commit()
        session.refresh(event)
    payload = serialize_event(event, rule)
    live.get_bus().publish("alert.fired", payload)
    if rule.webhook_url or rule.ntfy_url:
        _notify_pool.submit(_deliver, rule.webhook_url, rule.ntfy_url, rule.name, payload)
    return event


def serialize_event(event: AlertEvent, rule: AlertRule | None = None) -> dict[str, Any]:
    return {
        "alert_id": event.id,
        "rule_id": event.rule_id,
        "rule": rule.name if rule else None,
        "kind": event.kind,
        "subject": event.subject,
        "message": event.message,
        "value": event.value,
        "key_id": event.key_id,
        "created_at": iso_utc(event.created_at),
        "acknowledged_at": iso_utc(event.acknowledged_at),
    }


def _deliver(webhook_url: str | None, ntfy_url: str | None, rule_name: str, payload: dict[str, Any]) -> None:
    with httpx.Client(timeout=5.0, follow_redirects=False) as client:
        if webhook_url:
            try:
                client.post(webhook_url, json={"type": "alert", **payload})
            except httpx.HTTPError as exc:
                logger.warning("Alert webhook for rule %r failed: %s", rule_name, type(exc).__name__)
        if ntfy_url:
            try:
                client.post(
                    ntfy_url,
                    content=payload["message"].encode(),
                    headers={"Title": f"prompture-hub: {rule_name}", "Tags": "warning"},
                )
            except httpx.HTTPError as exc:
                logger.warning("Alert ntfy post for rule %r failed: %s", rule_name, type(exc).__name__)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _applies_to_key(rule: AlertRule, key_id: int) -> bool:
    return rule.key_id is None or rule.key_id == key_id


def evaluate_call(row: UsageRecord, meta: dict[str, Any] | None = None) -> None:
    """Check call-driven rules against a freshly written usage row. Never raises."""
    try:
        _evaluate_call(row, meta or {})
    except Exception:  # alerts must never break metering
        logger.exception("Alert evaluation failed")


def _evaluate_call(row: UsageRecord, meta: dict[str, Any]) -> None:
    rules = _enabled_rules(("key_spend", "fallback", "error", "provider_headroom"))
    if not rules:
        return
    served = row.served_by or row.model
    for rule in rules:
        if rule.kind == "key_spend" and _applies_to_key(rule, row.key_id) and row.cost_usd:
            _check_key_spend(rule, row.key_id)
        elif rule.kind == "fallback" and _applies_to_key(rule, row.key_id) and row.attempts > 1:
            if rule.target in (None, row.model):
                fire(
                    rule,
                    f"fallback:{row.model}",
                    f"{row.model} needed {row.attempts} attempts; served by {served}.",
                    value=float(row.attempts),
                    key_id=row.key_id,
                )
        elif rule.kind == "error" and _applies_to_key(rule, row.key_id) and row.status == "error":
            if rule.target in (None, row.model):
                fire(
                    rule,
                    f"error:{row.model}",
                    f"Call to {row.model} failed: {(row.error or 'unknown error')[:160]}",
                    key_id=row.key_id,
                )
        elif rule.kind == "provider_headroom":
            _check_headroom(rule, served, meta)


def _check_key_spend(rule: AlertRule, key_id: int) -> None:
    from .quotas import spend_in_window

    with get_session() as session:
        key = session.get(HubKey, key_id)
    if key is None or key.daily_spend_cap_usd <= 0:
        return
    period = (key.spend_period or "day").lower()
    fraction = spend_in_window(key.id, period) / key.daily_spend_cap_usd
    threshold = rule.threshold if rule.threshold is not None else default_threshold("key_spend")
    if fraction >= threshold:
        fire(
            rule,
            f"key:{key.id}",
            f"Key '{key.name}' has used {fraction:.0%} of its ${key.daily_spend_cap_usd:.2f} {period} cap.",
            value=round(fraction, 4),
            key_id=key.id,
        )


def _check_headroom(rule: AlertRule, served: str, meta: dict[str, Any]) -> None:
    data = meta.get("rate_limits")
    if not isinstance(data, dict) or rule.target not in (None, served):
        return
    try:
        from prompture.infra.rate_limits import LimitSnapshot
    except ImportError:
        return
    headroom, window = LimitSnapshot.from_dict(data).current_headroom()
    threshold = rule.threshold if rule.threshold is not None else default_threshold("provider_headroom")
    if headroom is not None and headroom < threshold:
        label = (window or "rate limit").replace("_", " ")
        fire(rule, served, f"{served} has {headroom:.0%} of its {label} window left.", value=round(headroom, 4))


def evaluate_accounts(snapshots: list[dict[str, Any]]) -> None:
    """Check ``balance_low`` rules against account snapshots. Never raises."""
    try:
        rules = _enabled_rules(("balance_low",))
        for rule in rules:
            if rule.threshold is None:
                continue
            for snap in snapshots:
                balance = snap.get("balance")
                if balance is None or rule.target not in (None, snap.get("source")):
                    continue
                if balance < rule.threshold:
                    currency = snap.get("currency") or ""
                    fire(
                        rule,
                        f"balance:{snap.get('source')}",
                        f"{snap.get('source')} balance is {balance:g} {currency}".rstrip() + f" (below {rule.threshold:g}).",
                        value=float(balance),
                    )
    except Exception:
        logger.exception("Account alert evaluation failed")

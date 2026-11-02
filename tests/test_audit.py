"""Audit log: actors, details and the /admin/audit listing; plus the 0010 migration."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

ADMIN = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("HUB_DB_PATH", tmp.name)
    monkeypatch.setenv("HUB_ADMIN_TOKEN", "test-token")
    from prompture_hub.settings import get_settings

    get_settings.cache_clear()
    from prompture_hub.storage import db as db_module

    db_module._engine = None
    db_module.init_db()
    yield
    get_settings.cache_clear()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client() -> TestClient:
    from prompture_hub.main import app

    return TestClient(app)


def _key(name: str = "app") -> int:
    r = _client().post("/admin/keys", headers=ADMIN, json={"name": name, "spend_cap_usd": 5.0})
    return r.json()["id"]


def _audit(**params) -> list[dict]:
    return _client().get("/admin/audit", headers=ADMIN, params=params).json()


def _device(name: str, scopes: list[str]) -> dict[str, str]:
    from prompture_hub.companion_auth import generate_device_token
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import DeviceToken

    token, hashed = generate_device_token()
    with get_session() as session:
        session.add(DeviceToken(name=name, hashed_secret=hashed, scopes=scopes))
        session.commit()
    return {"Authorization": f"Bearer {token}"}


def test_admin_update_is_audited_with_only_changed_fields():
    kid = _key()
    _client().patch(
        f"/admin/keys/{kid}", headers=ADMIN, json={"spend_cap_usd": 5.0, "rate_limit_per_min": 7}
    )
    [row] = _audit(action="key.update")
    assert (row["actor_kind"], row["actor_label"], row["key_id"]) == ("admin", "admin token", kid)
    assert row["details"] == {"before": {"rate_limit_per_min": 60}, "after": {"rate_limit_per_min": 7}}
    datetime.fromisoformat(row["created_at"])  # ISO with offset


def test_noop_update_writes_no_audit_row():
    kid = _key()
    _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": 60})
    assert _audit() == []


def test_v1_patch_audits_device_actor_and_other_fields():
    kid = _key()
    headers = _device("Juan's laptop", ["read", "control"])
    r = _client().patch(
        f"/v1/keys/{kid}", headers=headers,
        json={"rate_limit_per_min": 3, "spend_period": "month", "default_project": "demo", "route_override": "combo/x"},
    )
    assert r.status_code == 200, r.text
    [row] = _audit(key_id=kid)
    assert (row["actor_kind"], row["actor_label"]) == ("device", "Juan's laptop")
    assert row["actor_id"] is not None
    assert row["details"]["before"] == {
        "rate_limit_per_min": 60, "spend_period": "day", "default_project": None, "route_override": None,
    }
    assert row["details"]["after"] == {
        "rate_limit_per_min": 3, "spend_period": "month", "default_project": "demo", "route_override": "combo/x",
    }


def test_v1_patch_in_open_mode_is_local_dashboard():
    kid = _key()
    _client().patch(f"/v1/keys/{kid}", json={"rate_limit_per_min": 2})  # no dashboard login configured
    [row] = _audit(key_id=kid)
    assert (row["actor_kind"], row["actor_label"], row["actor_id"]) == ("user", "local dashboard", None)


def test_v1_patch_with_admin_token_is_admin_actor():
    kid = _key()
    _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={"rate_limit_per_min": 2})
    assert _audit(key_id=kid)[0]["actor_label"] == "admin token"


def test_reset_and_grant_are_audited():
    kid = _key()
    _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={"amount_usd": 2.5, "reason": "promo"})
    _client().post(f"/admin/keys/{kid}/reset-spend", headers=ADMIN, json={"reason": "fix"})
    reset, grant = _audit(key_id=kid)  # newest first
    assert reset["action"] == "key.spend_reset" and grant["action"] == "key.spend_grant"
    assert grant["details"]["amount_usd"] == 2.5 and grant["details"]["reason"] == "promo"
    assert grant["details"]["spent_before"] == 0.0 and grant["details"]["spent_after"] == -2.5
    assert reset["details"]["spent_before"] == -2.5 and reset["details"]["spent_after"] == 0.0
    assert reset["details"]["period"] == "day" and reset["details"]["window"]
    assert reset["actor_label"] == "admin token"


def test_audit_filters_and_limit():
    a, b = _key("a"), _key("b")
    for kid in (a, b):
        _client().post(f"/admin/keys/{kid}/grant", headers=ADMIN, json={"amount_usd": 1})
    _client().post(f"/admin/keys/{a}/reset-spend", headers=ADMIN)
    assert {r["key_id"] for r in _audit(key_id=a)} == {a}
    assert len(_audit(action="key.spend_grant")) == 2
    assert [r["action"] for r in _audit(key_id=a)] == ["key.spend_reset", "key.spend_grant"]
    assert len(_audit(limit=1)) == 1
    ids = [r["id"] for r in _audit()]
    assert ids == sorted(ids, reverse=True)
    assert _client().get("/admin/audit", headers=ADMIN, params={"limit": 501}).status_code == 422


def test_migration_0010_creates_and_drops_tables(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from prompture_hub.storage.db import _MIGRATIONS_DIR

    url = "sqlite:///" + str(tmp_path / "m.db")
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    engine = create_engine(url)

    command.upgrade(cfg, "head")
    insp = inspect(engine)
    assert {"auditlog", "spendadjustment"} <= set(insp.get_table_names())
    assert {c["name"] for c in insp.get_columns("spendadjustment")} == {
        "id", "key_id", "amount_usd", "kind", "reason", "created_at", "actor_label",
    }
    assert {c["name"] for c in insp.get_columns("auditlog")} == {
        "id", "created_at", "actor_kind", "actor_id", "actor_label", "action", "key_id", "details",
    }
    assert {i["name"] for i in insp.get_indexes("auditlog")} == {"ix_auditlog_created_at", "ix_auditlog_key_id"}

    command.downgrade(cfg, "a6d3e8f19c52")
    assert not {"auditlog", "spendadjustment"} & set(inspect(engine).get_table_names())

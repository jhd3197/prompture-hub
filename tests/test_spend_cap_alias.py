"""spend_cap_usd rename: deprecated daily_spend_cap_usd alias on input/output, migration 0011, audit."""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

ADMIN = {"Authorization": "Bearer test-token"}
OLD, NEW = "daily_spend_cap_usd", "spend_cap_usd"


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


def _create(**body):
    return _client().post("/admin/keys", headers=ADMIN, json={"name": "app", **body})


def _deprecated(r) -> bool:
    return r.headers.get("Deprecation") == "true" and "daily_spend_cap_usd" in r.headers.get("Warning", "")


def test_admin_create_old_name_sets_cap_and_flags_deprecation():
    r = _create(**{OLD: 3.5})
    assert r.status_code == 201, r.text
    assert (r.json()[NEW], r.json()[OLD]) == (3.5, 3.5)
    assert _deprecated(r)


def test_admin_create_new_name_no_deprecation_and_default():
    r = _create(**{NEW: 2.0})
    assert (r.json()[NEW], r.json()[OLD]) == (2.0, 2.0)
    assert "Deprecation" not in r.headers
    assert _create().json()[NEW] == 1.0


def test_admin_create_both_equal_ok_different_422_negative_and_null_rejected():
    assert _create(**{NEW: 2.0, OLD: 2.0}).status_code == 201
    r = _create(**{NEW: 2.0, OLD: 3.0})
    assert r.status_code == 422 and "disagree" in r.text
    assert _create(**{OLD: -1}).status_code == 422
    assert _create(**{NEW: None}).status_code == 422
    assert _create(**{OLD: None}).status_code == 422


def test_admin_patch_old_new_and_list_has_both():
    kid = _create(**{NEW: 1.0}).json()["id"]
    r = _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={OLD: 7.5})
    assert r.status_code == 200 and (r.json()[NEW], r.json()[OLD]) == (7.5, 7.5) and _deprecated(r)
    r = _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={NEW: 8.0})
    assert (r.json()[NEW], r.json()[OLD]) == (8.0, 8.0) and "Deprecation" not in r.headers
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={NEW: 9.0, OLD: 9.0}).status_code == 200
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={NEW: 1.0, OLD: 2.0}).status_code == 422
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={OLD: -1}).status_code == 422
    assert _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={OLD: None}).status_code == 400
    [listed] = _client().get("/admin/keys", headers=ADMIN).json()
    assert (listed[NEW], listed[OLD]) == (9.0, 9.0)


def test_v1_patch_old_name_keeps_working_for_prompture_desk():
    kid = _create().json()["id"]
    r = _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={OLD: 0.5, "route_override": ""})
    assert r.status_code == 200, r.text
    assert (r.json()[NEW], r.json()[OLD]) == (0.5, 0.5) and _deprecated(r)
    r = _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={NEW: 0.75})
    assert (r.json()[NEW], r.json()[OLD]) == (0.75, 0.75) and "Deprecation" not in r.headers
    assert _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={NEW: 1, OLD: 1}).status_code == 200
    assert _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={NEW: 1, OLD: 2}).status_code == 422
    assert _client().patch(f"/v1/keys/{kid}", headers=ADMIN, json={OLD: None}).status_code == 400


def test_limits_shape_unchanged():
    _create(**{NEW: 2.0})
    [key] = _client().get("/v1/limits?accounts=false", headers=ADMIN).json()["keys"]
    assert set(key) == {"id", "name", "default_project", "paused", "route_override", "spend", "rate"}
    assert set(key["spend"]) == {
        "period", "cap_usd", "spent_usd", "reserved_usd", "fraction_used", "resets_at", "source",
    }
    assert key["spend"]["cap_usd"] == 2.0


def test_audit_uses_new_name_and_legacy_rows_still_read():
    kid = _create(**{NEW: 1.0}).json()["id"]
    _client().patch(f"/admin/keys/{kid}", headers=ADMIN, json={OLD: 4.0})
    [row] = _client().get("/admin/audit", headers=ADMIN, params={"action": "key.update"}).json()
    assert row["details"] == {"before": {NEW: 1.0}, "after": {NEW: 4.0}}

    from prompture_hub import audit
    from prompture_hub.audit import ADMIN_ACTOR

    audit.record(ADMIN_ACTOR, "key.update", kid, {"before": {OLD: 1.0}, "after": {OLD: 2.0}})
    rows = _client().get("/admin/audit", headers=ADMIN, params={"action": "key.update"}).json()
    assert any(r["details"] == {"before": {OLD: 1.0}, "after": {OLD: 2.0}} for r in rows)


def test_migration_0011_renames_column_preserving_data(tmp_path):
    from alembic import command
    from alembic.config import Config

    from prompture_hub.storage.db import _MIGRATIONS_DIR

    path = str(tmp_path / "m.db")
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", "sqlite:///" + path)

    def cols() -> dict[str, tuple[int, object]]:
        with sqlite3.connect(path) as c:
            return {r[1]: (r[3], r[4]) for r in c.execute("PRAGMA table_info(hubkey)")}

    command.upgrade(cfg, "b8e41c07d3a9")
    before = cols()
    assert OLD in before and NEW not in before
    with sqlite3.connect(path) as c:
        c.execute(
            "INSERT INTO hubkey (name, hashed_secret, allowed_models, daily_spend_cap_usd, spend_period, "
            "rate_limit_per_min, allowed_ips, created_at) VALUES ('k', 'h', '[]', 4.25, 'week', 60, '[]', '2026-01-01')"
        )

    command.upgrade(cfg, "head")
    after = cols()
    assert NEW in after and OLD not in after
    assert after[NEW] == before[OLD]  # notnull flag and default preserved
    with sqlite3.connect(path) as c:
        assert c.execute(f"SELECT {NEW} FROM hubkey").fetchone() == (4.25,)

    command.downgrade(cfg, "b8e41c07d3a9")
    assert OLD in cols() and NEW not in cols()
    with sqlite3.connect(path) as c:
        assert c.execute(f"SELECT {OLD} FROM hubkey").fetchone() == (4.25,)

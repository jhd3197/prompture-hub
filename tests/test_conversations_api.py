"""SPA-facing /api/conversations endpoints.

Verifies user-scoped listing, ownership-checked detail/delete, and the
shape of the totals block.
"""

from __future__ import annotations

import os
import tempfile

import pytest


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
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _client():
    from fastapi.testclient import TestClient

    from prompture_hub.main import app
    return TestClient(app)


def _new_key(name: str = "conv-test") -> str:
    r = _client().post(
        "/admin/keys",
        headers={"Authorization": "Bearer test-token"},
        json={
            "name": name,
            "allowed_models": ["stub/model"],
            "daily_spend_cap_usd": 10.0,
            "rate_limit_per_min": 1000,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["key"]


def _make_conversation(plaintext: str, **kwargs) -> str:
    """Create a conversation through the public /v1 surface, return its id."""
    r = _client().post(
        "/v1/conversations",
        headers={"Authorization": f"Bearer {plaintext}"},
        json=kwargs,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _append_assistant_message(
    conv_id: str, content: str = "hi", tokens: int = 10, cost: float = 0.001,
) -> None:
    """Stamp an assistant message directly so the totals block has data."""
    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import Message
    with get_session() as session:
        session.add(Message(
            conversation_id=conv_id,
            role="assistant",
            content=content,
            prompt_tokens=tokens // 2,
            completion_tokens=tokens - tokens // 2,
            total_tokens=tokens,
            cost_usd=cost,
        ))
        session.commit()


def test_list_returns_user_conversations():
    pt = _new_key()
    _make_conversation(pt, title="seo-audit-run", system="You audit SEO.")
    _make_conversation(pt, title="data-extract")

    r = _client().get("/api/conversations")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    titles = {row["title"] for row in rows}
    assert titles == {"seo-audit-run", "data-extract"}


def test_list_sorted_by_updated_desc():
    pt = _new_key()
    _make_conversation(pt, title="oldest")
    _make_conversation(pt, title="middle")
    _make_conversation(pt, title="newest")

    r = _client().get("/api/conversations")
    rows = r.json()
    assert [r["title"] for r in rows] == ["newest", "middle", "oldest"]


def test_detail_returns_messages_and_totals():
    pt = _new_key()
    cid = _make_conversation(pt, title="extraction", system="Be terse.")
    _append_assistant_message(cid, content="ok", tokens=30, cost=0.002)
    _append_assistant_message(cid, content="done", tokens=20, cost=0.001)

    r = _client().get(f"/api/conversations/{cid}")
    assert r.status_code == 200
    detail = r.json()
    assert detail["title"] == "extraction"
    # system + 2 assistant
    assert detail["totals"]["message_count"] == 3
    assert detail["totals"]["total_tokens"] == 50
    assert detail["totals"]["cost_usd"] == pytest.approx(0.003, rel=1e-6)
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["system", "assistant", "assistant"]


def test_detail_404_for_unknown_id():
    r = _client().get("/api/conversations/conv_does_not_exist")
    assert r.status_code == 404


def test_delete_removes_conversation_and_messages():
    pt = _new_key()
    cid = _make_conversation(pt, title="to-delete")
    _append_assistant_message(cid)

    r = _client().delete(f"/api/conversations/{cid}")
    assert r.status_code == 204

    r2 = _client().get(f"/api/conversations/{cid}")
    assert r2.status_code == 404

    # And no orphan messages.
    from sqlmodel import select

    from prompture_hub.storage.db import get_session
    from prompture_hub.storage.models import Message
    with get_session() as session:
        leftover = session.exec(
            select(Message).where(Message.conversation_id == cid)
        ).all()
    assert leftover == []

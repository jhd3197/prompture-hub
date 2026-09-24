"""`prompture-hub setup <tool>` output and config writing."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from prompture_hub.setup_tools import PLACEHOLDER_KEY, TOOLS, build_plan


@pytest.mark.parametrize("tool", sorted(TOOLS))
def test_every_tool_renders(tool):
    text = build_plan(tool, base_url="http://hub:1984/", key="ph_abc", model="combo/chat").render()
    assert "ph_abc" in text
    assert "http://hub:1984" in text
    assert "hub:1984//" not in text  # trailing slash normalized


def test_claude_code_env_and_placeholder():
    plan = build_plan("claude-code", base_url="http://localhost:1984", key=None, model="auto/best", small_model="auto/cheap")
    assert plan.env["ANTHROPIC_BASE_URL"] == "http://localhost:1984"
    assert plan.env["ANTHROPIC_AUTH_TOKEN"] == PLACEHOLDER_KEY
    assert plan.env["ANTHROPIC_MODEL"] == "auto/best"
    assert plan.env["ANTHROPIC_SMALL_FAST_MODEL"] == "auto/cheap"
    text = plan.render()
    assert 'export ANTHROPIC_AUTH_TOKEN=\'<your-hub-key>\'' in text
    assert '$env:ANTHROPIC_MODEL = "auto/best"' in text


def test_claude_code_write_merges_and_backs_up(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"theme": "dark", "env": {"KEEP": "1"}}))

    plan = build_plan("claude-code", base_url="http://h:1", key="ph_k", model="m")
    msg = plan.writer()

    data = json.loads(settings.read_text())
    assert data["theme"] == "dark"
    assert data["env"]["KEEP"] == "1"
    assert data["env"]["ANTHROPIC_AUTH_TOKEN"] == "ph_k"
    assert (tmp_path / ".claude" / "settings.json.bak").exists()
    assert "backed up" in msg


def test_write_unsupported_tool_exits(capsys):
    from prompture_hub.main import cli

    with pytest.raises(SystemExit) as ei:
        cli(["setup", "aider", "--key", "ph_k", "--write"])
    assert ei.value.code == 1


def test_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool"):
        build_plan("vim", base_url="x", key=None, model="m")


def test_create_key_cli(monkeypatch, capsys):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    monkeypatch.setenv("HUB_DB_PATH", tmp.name)
    from prompture_hub.settings import get_settings
    get_settings.cache_clear()
    from prompture_hub.storage import db as db_module
    db_module._engine = None
    try:
        from prompture_hub.main import cli

        cli(["setup", "openai", "--create-key", "--base-url", "http://h:1"])
        out = capsys.readouterr().out
        assert "Created hub key 'setup:openai'" in out
        assert "OPENAI_API_KEY=ph_" in out

        from sqlmodel import select

        from prompture_hub.storage.db import get_session
        from prompture_hub.storage.models import HubKey

        with get_session() as session:
            names = [k.name for k in session.exec(select(HubKey)).all()]
        assert names == ["setup:openai"]
    finally:
        db_module._engine = None
        get_settings.cache_clear()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

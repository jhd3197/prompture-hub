"""``prompture-hub setup <tool>`` - point coding tools and SDKs at the hub.

Prints the environment variables / config snippet each tool needs. Only
``--write`` touches files, and only where the tool has a documented,
mergeable config (Claude Code's ``settings.json``); the previous file is
backed up next to it first.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER_KEY = "<your-hub-key>"


@dataclass
class SetupPlan:
    tool: str
    summary: str
    env: dict[str, str]
    snippet: str | None = None
    snippet_path: str | None = None
    notes: tuple[str, ...] = ()
    writer: Callable[[], str] | None = None

    def render(self) -> str:
        lines = [f"# {self.tool}: {self.summary}", ""]
        if self.env:
            lines.append("# macOS / Linux")
            lines += [f"export {k}={_sh(v)}" for k, v in self.env.items()]
            lines.append("")
            lines.append("# Windows PowerShell")
            lines += [f'$env:{k} = "{v}"' for k, v in self.env.items()]
            lines.append("")
        if self.snippet:
            lines.append(f"# {self.snippet_path}" if self.snippet_path else "# config")
            lines.append(self.snippet.rstrip())
            lines.append("")
        lines += [f"# {n}" for n in self.notes]
        return "\n".join(lines).rstrip() + "\n"


def _sh(value: str) -> str:
    return value if value and all(c.isalnum() or c in "-_./:" for c in value) else f"'{value}'"


def _claude_code(base: str, key: str, model: str, small: str) -> SetupPlan:
    env = {
        "ANTHROPIC_BASE_URL": base,
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": small,
        "ANTHROPIC_SMALL_FAST_MODEL": small,
    }
    settings_path = Path.home() / ".claude" / "settings.json"

    def write() -> str:
        data: dict = {}
        backup: Path | None = None
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
            backup = settings_path.with_suffix(".json.bak")
            shutil.copy2(settings_path, backup)
        data.setdefault("env", {}).update(env)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        suffix = f"; previous file backed up to {backup}" if backup else ""
        return f"Updated {settings_path} (env block){suffix}"

    return SetupPlan(
        "claude-code",
        "Claude Code talks to the hub's Anthropic-compatible /v1/messages.",
        env,
        notes=(
            "Any hub model works: combo/<name>, auto/cheap, openai/gpt-4o, ...",
            f"--write merges these into {settings_path} instead of your shell.",
        ),
        writer=write,
    )


def _codex(base: str, key: str, model: str, small: str) -> SetupPlan:
    snippet = f'''model = "{model}"
model_provider = "prompture-hub"

[model_providers.prompture-hub]
name = "prompture-hub"
base_url = "{base}/v1"
env_key = "PROMPTURE_HUB_API_KEY"
wire_api = "chat"'''
    return SetupPlan(
        "codex",
        "Codex CLI through the hub's OpenAI-compatible chat completions.",
        {"PROMPTURE_HUB_API_KEY": key},
        snippet,
        "~/.codex/config.toml (top-level keys must come before any [table])",
    )


def _aider(base: str, key: str, model: str, small: str) -> SetupPlan:
    return SetupPlan(
        "aider",
        "Aider via its OpenAI-compatible provider.",
        {"OPENAI_API_BASE": f"{base}/v1", "OPENAI_API_KEY": key},
        notes=(f"Run: aider --model openai/{model} --weak-model openai/{small}",),
    )


def _cursor(base: str, key: str, model: str, small: str) -> SetupPlan:
    return SetupPlan(
        "cursor",
        "Cursor custom OpenAI endpoint (configured in the app, not a file).",
        {},
        notes=(
            "Settings > Models > API Keys > OpenAI API Key:",
            f"    key:      {key}",
            f"    Override OpenAI Base URL: {base}/v1",
            f"Then add a custom model named: {model}",
            "Cursor calls the endpoint from its own servers, so the hub must be reachable",
            "from the internet (a tunnel), not only on localhost.",
        ),
    )


def _continue(base: str, key: str, model: str, small: str) -> SetupPlan:
    snippet = f"""models:
  - name: Prompture Hub ({model})
    provider: openai
    model: {model}
    apiBase: {base}/v1
    apiKey: {key}"""
    return SetupPlan("continue", "Continue (VS Code / JetBrains).", {}, snippet, "~/.continue/config.yaml")


def _openai(base: str, key: str, model: str, small: str) -> SetupPlan:
    return SetupPlan(
        "openai",
        "Any OpenAI SDK or OpenAI-compatible tool.",
        {"OPENAI_BASE_URL": f"{base}/v1", "OPENAI_API_KEY": key},
        notes=(f'client.chat.completions.create(model="{model}", ...)',),
    )


def _anthropic(base: str, key: str, model: str, small: str) -> SetupPlan:
    return SetupPlan(
        "anthropic",
        "Any Anthropic SDK client.",
        {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": key},
        notes=(f'client.messages.create(model="{model}", ...)',),
    )


TOOLS: dict[str, Callable[[str, str, str, str], SetupPlan]] = {
    "claude-code": _claude_code,
    "codex": _codex,
    "aider": _aider,
    "cursor": _cursor,
    "continue": _continue,
    "openai": _openai,
    "anthropic": _anthropic,
}


def build_plan(tool: str, *, base_url: str, key: str | None, model: str, small_model: str | None = None) -> SetupPlan:
    if tool not in TOOLS:
        raise ValueError(f"Unknown tool '{tool}'. Choose one of: {', '.join(TOOLS)}")
    return TOOLS[tool](base_url.rstrip("/"), key or PLACEHOLDER_KEY, model, small_model or model)


def create_setup_key(tool: str) -> str:
    """Mint a hub key named after the tool in the local database. Returns the plaintext."""
    from .auth import generate_key
    from .storage.db import get_session, init_db
    from .storage.models import HubKey

    init_db()
    plaintext, hashed = generate_key()
    with get_session() as session:
        session.add(HubKey(name=f"setup:{tool}", hashed_secret=hashed, allowed_models=[]))
        session.commit()
    return plaintext

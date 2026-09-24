"""``prompture-hub setup <tool>`` - point coding tools and SDKs at the hub.

Prints the environment variables / config snippet each tool needs. Only
``--write`` touches files, and only where the tool has a documented,
mergeable config (Claude Code's ``settings.json``); the previous file is
backed up next to it first.

``--project NAME`` (or ``--project .`` for the current folder's name) makes
the tool send ``X-Project: NAME`` so the hub attributes its spend to that
project. Tools that cannot send custom headers get a note to use a key with
a default project instead (``--create-key`` sets it).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER_KEY = "<your-hub-key>"
PROJECT_HEADER = "X-Project"


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


def _claude_code(base: str, key: str, model: str, small: str, project: str | None = None) -> SetupPlan:
    env = {
        "ANTHROPIC_BASE_URL": base,
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": small,
        "ANTHROPIC_SMALL_FAST_MODEL": small,
    }
    if project:
        env["ANTHROPIC_CUSTOM_HEADERS"] = f"{PROJECT_HEADER}: {project}"
        # A project belongs to one folder, so its settings go in that folder's
        # local settings file rather than the user-wide one.
        settings_path = Path.cwd() / ".claude" / "settings.local.json"
    else:
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


def _codex(base: str, key: str, model: str, small: str, project: str | None = None) -> SetupPlan:
    snippet = f'''model = "{model}"
model_provider = "prompture-hub"

[model_providers.prompture-hub]
name = "prompture-hub"
base_url = "{base}/v1"
env_key = "PROMPTURE_HUB_API_KEY"
wire_api = "responses"'''
    if project:
        snippet += f'\nhttp_headers = {{ "{PROJECT_HEADER}" = "{project}" }}'
    return SetupPlan(
        "codex",
        "Codex CLI through the hub's OpenAI Responses API (/v1/responses).",
        {"PROMPTURE_HUB_API_KEY": key},
        snippet,
        "~/.codex/config.toml (top-level keys must come before any [table])",
    )


def _aider(base: str, key: str, model: str, small: str, project: str | None = None) -> SetupPlan:
    return SetupPlan(
        "aider",
        "Aider via its OpenAI-compatible provider.",
        {"OPENAI_API_BASE": f"{base}/v1", "OPENAI_API_KEY": key},
        notes=(f"Run: aider --model openai/{model} --weak-model openai/{small}", *_key_project_note(project)),
    )


def _cursor(base: str, key: str, model: str, small: str, project: str | None = None) -> SetupPlan:
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
            *_key_project_note(project),
        ),
    )


def _continue(base: str, key: str, model: str, small: str, project: str | None = None) -> SetupPlan:
    snippet = f"""models:
  - name: Prompture Hub ({model})
    provider: openai
    model: {model}
    apiBase: {base}/v1
    apiKey: {key}"""
    if project:
        snippet += f"""
    requestOptions:
      headers:
        {PROJECT_HEADER}: {project}"""
    return SetupPlan("continue", "Continue (VS Code / JetBrains).", {}, snippet, "~/.continue/config.yaml")


def _openai(base: str, key: str, model: str, small: str, project: str | None = None) -> SetupPlan:
    notes = [f'client.chat.completions.create(model="{model}", ...)']
    if project:
        notes.append(f'OpenAI(default_headers={{"{PROJECT_HEADER}": "{project}"}}) attributes spend to the project.')
    return SetupPlan(
        "openai",
        "Any OpenAI SDK or OpenAI-compatible tool.",
        {"OPENAI_BASE_URL": f"{base}/v1", "OPENAI_API_KEY": key},
        notes=tuple(notes),
    )


def _anthropic(base: str, key: str, model: str, small: str, project: str | None = None) -> SetupPlan:
    notes = [f'client.messages.create(model="{model}", ...)']
    if project:
        notes.append(f'Anthropic(default_headers={{"{PROJECT_HEADER}": "{project}"}}) attributes spend to the project.')
    return SetupPlan(
        "anthropic",
        "Any Anthropic SDK client.",
        {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": key},
        notes=tuple(notes),
    )


def _key_project_note(project: str | None) -> tuple[str, ...]:
    if not project:
        return ()
    return (
        f"This tool can't send custom headers; attribute its spend to '{project}' by giving",
        "its key a default project (setup --create-key --project does this).",
    )


def resolve_project_arg(value: str | None) -> str | None:
    """``"."`` means the current folder's name; anything else is used as given."""
    if value is None:
        return None
    from .metering import clean_project

    return clean_project(Path.cwd().name if value.strip() == "." else value)


TOOLS: dict[str, Callable[..., SetupPlan]] = {
    "claude-code": _claude_code,
    "codex": _codex,
    "aider": _aider,
    "cursor": _cursor,
    "continue": _continue,
    "openai": _openai,
    "anthropic": _anthropic,
}


def build_plan(
    tool: str,
    *,
    base_url: str,
    key: str | None,
    model: str,
    small_model: str | None = None,
    project: str | None = None,
) -> SetupPlan:
    if tool not in TOOLS:
        raise ValueError(f"Unknown tool '{tool}'. Choose one of: {', '.join(TOOLS)}")
    return TOOLS[tool](base_url.rstrip("/"), key or PLACEHOLDER_KEY, model, small_model or model, project)


def create_setup_key(tool: str, project: str | None = None) -> str:
    """Mint a hub key named after the tool in the local database. Returns the plaintext.

    With *project*, the key's calls default to that project, which covers
    tools that cannot send an ``X-Project`` header.
    """
    from .auth import generate_key
    from .storage.db import get_session, init_db
    from .storage.models import HubKey

    init_db()
    plaintext, hashed = generate_key()
    with get_session() as session:
        name = f"setup:{tool}:{project}" if project else f"setup:{tool}"
        session.add(HubKey(name=name, hashed_secret=hashed, allowed_models=[], default_project=project))
        session.commit()
    return plaintext

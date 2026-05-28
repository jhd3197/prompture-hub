# prompture-hub

Self-hosted gateway over [Prompture](https://github.com/jhd3197/prompture)'s multi-provider LLM driver registry. Think OpenRouter, except *you* control the keys, the metering, and the trust boundary.

## Why this exists

You have provider API keys (OpenAI, Anthropic, Groq, Ollama, etc.). You want to let other apps — including apps you don't fully trust — call LLMs *through* your keys, with per-app limits and observability, **without** ever handing those apps the real provider keys.

`prompture-hub` does that by:

1. Holding the real provider keys server-side (loaded once from `.env`)
2. Issuing **hub-scoped API keys** that untrusted apps use
3. Enforcing per-key allowed-model whitelists, daily spend caps, and rate limits
4. Recording every call (cost, latency, tokens) for the dashboard

The untrusted app never sees `OPENAI_API_KEY` (or any other real provider secret). If you revoke its hub key, it's locked out instantly — no scrambling to rotate provider keys.

## Status

**v0.0.1 (scaffold)** — solo / localhost / SQLite. The architecture (auth, key model, storage) is designed to extend to multi-user and public deployment later without rewriting v0.1 surface.

## Quickstart

```bash
git clone https://github.com/jhd3197/prompture-hub
cd prompture-hub
pip install -e ".[dev]"

cp .env.example .env
# Fill in: HUB_ADMIN_TOKEN, plus whatever provider keys you want available
# (OPENAI_API_KEY, ANTHROPIC_API_KEY, OLLAMA_BASE_URL, ...)

uvicorn prompture_hub.main:app --reload
```

Then create a scoped key for an untrusted app:

```bash
curl -X POST http://localhost:1984/admin/keys \
  -H "Authorization: Bearer $HUB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sketchy-app",
    "allowed_models": ["ollama/llama3.1:8b"],
    "daily_spend_cap_usd": 1.0,
    "rate_limit_per_min": 30
  }'
```

The response includes the plaintext key once — copy it now, you cannot retrieve it again. Hand it to the untrusted app. From inside that app:

```bash
curl http://localhost:1984/v1/chat/completions \
  -H "Authorization: Bearer ph_xxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ollama/llama3.1:8b",
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

The dashboard lives at `http://localhost:1984/` and shows recent keys, recent calls, and 24-hour spend.

## Two API surfaces

| Surface | Endpoints | Use case |
|---|---|---|
| **OpenAI-compatible** | `/v1/chat/completions`, `/v1/models` | Drop-in for any OpenAI-SDK client. Maximum compatibility. |
| **Prompture-native** | `/v1/extract` | Structured extraction with JSON Schema. Exposes Prompture's `ask_for_json` + strategies (`provider_native`, `tool_call`, `prompted_repair`) over HTTP. |
| **Sessions** | `/v1/conversations` (CRUD) + `conversation_id` on `/v1/chat/completions` | Resumable chat: a later request replays prior turns server-side so the client doesn't need to ship full history. |

### Resumable sessions

Create a conversation, then reference its id on subsequent `/v1/chat/completions` calls:

```bash
# 1. open a session (optionally with a system prompt)
curl -X POST http://localhost:1984/v1/conversations \
  -H "Authorization: Bearer ph_xxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"title": "seo-audit-run", "system": "You are an SEO auditor."}'
# => { "id": "conv_...", ... }

# 2. talk to it; prior turns are loaded automatically
curl http://localhost:1984/v1/chat/completions \
  -H "Authorization: Bearer ph_xxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ollama/llama3.1:8b",
    "conversation_id": "conv_...",
    "messages": [{"role": "user", "content": "Audit example.com"}]
  }'

# 3. inspect history later
curl http://localhost:1984/v1/conversations/conv_... \
  -H "Authorization: Bearer ph_xxxxxxxxxxxx"
```

Set `"persist": false` on a chat request to use the session as read-only history without recording the new turn. Conversations are scoped to the HubKey that created them.

## Run on Linux with Docker

```bash
cp .env.example .env
# fill HUB_ADMIN_TOKEN + provider keys

docker compose up -d --build
docker compose logs -f hub
curl http://localhost:1984/health
```

The container:

- Runs as non-root user `hub` (uid 10001)
- Persists SQLite at `/data/prompture_hub.db` via the `hub_data` named volume
- Binds `0.0.0.0:1984` inside the container (compose maps to host `1984`)
- Has a `/health` healthcheck (curl-based, 30s interval)

For a public deployment, put it behind nginx/Caddy with TLS and rate limits — don't expose port 1984 to the internet directly.

## Architecture

```
prompture-hub/
├── src/prompture_hub/
│   ├── main.py              FastAPI app factory + lifespan + uvicorn CLI
│   ├── settings.py          HubSettings (admin_token, db_path, host/port)
│   ├── auth.py              require_admin + require_hub_key dependencies
│   ├── routers/
│   │   ├── openai_compat.py /v1/chat/completions, /v1/models
│   │   ├── extract.py       /v1/extract (Prompture-native)
│   │   ├── admin.py         /admin/keys CRUD + /admin/usage
│   │   └── dashboard.py     server-rendered HTML dashboard (Jinja2)
│   ├── storage/
│   │   ├── db.py            SQLite engine + session factory
│   │   └── models.py        HubKey, UsageRecord (SQLModel tables)
│   ├── templates/           Jinja2 dashboard templates (Tailwind via CDN)
│   └── static/
└── tests/
```

## Security model

- **Hub-issued keys** are 32-byte URL-safe tokens, prefixed `ph_`. Only the SHA-256 hash is stored; plaintext is returned to the caller once at creation.
- **Admin endpoints** (`/admin/*`) require `Authorization: Bearer $HUB_ADMIN_TOKEN`. Different credential from hub-issued keys — separation of duties.
- **Real provider keys** (`OPENAI_API_KEY`, etc.) are read directly by Prompture's drivers from environment. They never appear in any HTTP response.
- **Localhost-only by default**: `HUB_HOST=127.0.0.1`. Public exposure requires reverse proxy + TLS + rate-limit middleware (v0.2).

## Roadmap

- **v0.1** — scaffold, OpenAI-compat (non-streaming), extract, scoped keys, embedded Jinja dashboard
- **v0.2** — SSE streaming, /v1/embeddings, rate-limit middleware, key creation UI form, React frontend matching CachiBot's stack
- **v0.3** — multi-user (`/admin/users`, OAuth admin, per-user key namespacing)
- **v0.4** — hosted-ready (Docker image, Postgres backend, public deploy guide, audit log)

## License

MIT

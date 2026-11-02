# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Billing reconciliation: `GET /admin/billing/reconciliation?period=day|week|month&refresh=false` compares hub-recorded spend with OpenAI/Anthropic organization cost reports (`OPENAI_ADMIN_KEY` / `ANTHROPIC_ADMIN_KEY`) and OpenRouter usage, reports DeepSeek/Moonshot balances, and flags mismatches. Provider failures only affect their own row.
- Dashboard: a Billing page (`/billing`, backed by `GET /api/billing/reconciliation`) with period selector, refresh, status badges and per-provider caveats.
- Settings `HUB_BILLING_TOLERANCE_PCT` (10), `HUB_BILLING_TOLERANCE_USD` (0.50) and `HUB_BILLING_CACHE_SECONDS` (300).
- Admin cap controls: `PATCH /admin/keys/{id}` changes a key's spend cap, period and rate limit (admin token).
- `rate_limit_per_min` can now be changed through `PATCH /v1/keys/{id}` and is part of the returned key state.
- Dashboard: an "Edit limits" button on each active key opens a modal to edit spend cap, period and rate limit.
- `POST /admin/keys/{id}/reset-spend` and `POST /admin/keys/{id}/grant` credit a key's spend in the current cap window only; they expire when the window rolls over. `GET /admin/keys/{id}/adjustments` lists them.
- `spent_in_window` on `GET /admin/keys` items.
- Audit log of key changes (who, when, before/after) with `GET /admin/audit`.
- Migration `0010`: new `spendadjustment` and `auditlog` tables.

### Changed
- The cap window spend (used by quota checks, `/v1/limits` and alerts) now includes spend adjustments made in the window, and can be negative after a grant.
- Renamed the key spend cap from `daily_spend_cap_usd` to `spend_cap_usd` (the cap is not daily; see `spend_period`). Migration `0011` renames the `hubkey` column in place (batch mode, data kept, reversible with `alembic downgrade`); it runs automatically on boot. Back up the database before upgrading.
- Audit rows written from now on use `spend_cap_usd` in `before`/`after`; rows written earlier keep `daily_spend_cap_usd` and are returned unchanged.
- The `key.updated` live event `changes` carries both names when the cap changed.

### Deprecated
- `daily_spend_cap_usd` is a deprecated alias of `spend_cap_usd`. Request bodies of `POST /admin/keys`, `PATCH /admin/keys/{id}`, `PATCH /v1/keys/{id}` and `POST /api/keys` accept either name (sending both with different values returns 422); using the old name adds `Deprecation: true` and a `Warning: 299` header and logs once per process. Key objects in responses return both names with the same value. `/v1/limits` is unchanged. Older hub clients and prompture-desk keep working. The alias will not be removed before a future minor version.

### Hardened
- Cost reservations: each admitted call holds an estimated cost until it settles, so concurrent and streaming calls can no longer overshoot a spend cap, and in-flight calls count toward the rate limit. Applies to chat completions, embeddings, Anthropic messages, Responses and `/v1/extract`. The ledger is process-local (one hub process). Coding-agent runs are not reserved.
- `/v1/embeddings` is quota-gated with the whitelist, paused-provider and reservation checks; cost is computed from Prompture's rates when the driver reports none.
- 402/429 responses keep `detail` and add a machine-readable `error` object (`spend_cap_exceeded`, `spend_cap_would_exceed`, `rate_limit_exceeded`, `pricing_unknown`) with the period, cap, spent, reserved and window reset time.
- `HUB_UNKNOWN_PRICING` (`block` by default): models with no known prices are refused with 402 `pricing_unknown`; `warn` allows them with an `X-Hub-Cost-Warning` header. Local providers and explicit zero-rate models are not flagged. This changes behavior: unpriced models (including custom endpoints) are blocked unless you set `warn`.
- New settings `HUB_DEFAULT_OUTPUT_TOKEN_ESTIMATE` (1024) and `HUB_RESERVATION_TTL_SECONDS` (900); `/v1/limits` reports `reserved_usd`.

## [0.0.3]

### Changed
- Require `prompture>=1.16` (was `>=1.13`).
- Sync the version everywhere: `pyproject.toml`, `VERSION`, README and `prompture_hub.__version__` (which was stale at 0.0.1).
- README status section updated for the current state.

### Fixed
- `test_weekly_cap_counts_yesterday` failed on Mondays because "yesterday" fell in the previous week. The weekly and monthly quota tests now seed spend at the start of the cap window, so they no longer depend on the day they run.

### Notes
- The PyPI release pipeline previously failed because the PyPI Trusted Publisher was not configured (a PyPI-side setting). As a result, versions after 0.0.1 were never uploaded to PyPI. The required setup is documented in `.github/workflows/release.yml`.

## [0.0.2]

### Added
- Companion API built on `prompture.companion`: device pairing, `/v1/limits` and `/v1/spend`, live call events at `/v1/live`, pausing keys or a provider hub-wide, and switching a key's route.
- Projects: usage is attributed to projects.
- Alert rules with webhook and ntfy delivery.
- Custom OpenAI-compatible endpoints.
- Anthropic Messages API and OpenAI Responses API, plus a metered `/v1/embeddings` endpoint.
- Chat completions built on `prompture.gateway`, with reasoning replay and optional prompt compression.
- Key policies: IP allowlists and expiry.
- Usage analytics (API and UI page) and key access controls in the UI.
- `prompture-hub setup <tool>` command.
- Pairing, devices, alerts and endpoints in the UI.
- Automated releases: auto-bump on merge to `main` and version sync.

### Fixed
- Chat metering and extract payload.
- 204 routes now return an explicit empty response.
- CI lint, agent stream timeouts, and npm on Windows builds.

## [0.0.1]

### Added
- Initial gateway: hub-scoped API keys, per-key model allowlists, spend caps (day, week, month) and rate limits, with usage recording.
- OpenAI-compatible `/v1/chat/completions` with SSE streaming.
- React dashboard with Google and GitHub OAuth login, key management, models page, conversations, and coding-agent runs.
- Alembic migrations; pip-installable package with bundled SPA.

# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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

# syntax=docker/dockerfile:1.7

# --- frontend build stage ---
FROM node:20-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


# --- python runtime ---
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
# Migrations live under src/prompture_hub/migrations (shipped with the package),
# so there's no separate alembic/ dir to copy.

# Bring in the built SPA bundle from the frontend stage.
COPY --from=frontend /build/src/prompture_hub/static/app ./src/prompture_hub/static/app

RUN pip install --upgrade pip \
 && pip install .

RUN useradd --uid 10001 --create-home --shell /bin/bash hub \
 && mkdir -p /data \
 && chown -R hub:hub /data /app

USER hub

ENV HUB_HOST=0.0.0.0 \
    HUB_PORT=1984 \
    HUB_DB_PATH=/data/prompture_hub.db

EXPOSE 1984

VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:1984/health || exit 1

CMD ["python", "-m", "uvicorn", "prompture_hub.main:app", "--host", "0.0.0.0", "--port", "1984"]

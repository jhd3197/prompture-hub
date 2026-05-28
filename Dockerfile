# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

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

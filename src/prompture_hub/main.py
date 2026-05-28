"""FastAPI app factory and console-script entrypoint for prompture-hub."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import admin, conversations, dashboard, extract, openai_compat
from .settings import get_settings
from .storage.db import init_db

logger = logging.getLogger("prompture_hub")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    logger.info("prompture-hub ready on %s:%d", settings.host, settings.port)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="prompture-hub",
        description=(
            "Self-hosted gateway over Prompture's multi-provider LLM driver registry. "
            "Hub-issued scoped keys map to real provider keys server-side."
        ),
        version="0.0.1",
        lifespan=lifespan,
    )

    app.include_router(openai_compat.router, prefix="/v1", tags=["openai-compat"])
    app.include_router(extract.router, prefix="/v1", tags=["prompture-native"])
    app.include_router(conversations.router, prefix="/v1", tags=["conversations"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])
    app.include_router(dashboard.router, tags=["dashboard"])

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app


app = create_app()


def cli() -> None:
    """Console-script entry point: runs uvicorn against the app."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "prompture_hub.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )

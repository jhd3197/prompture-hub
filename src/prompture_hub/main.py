"""FastAPI app factory and console-script entrypoint for prompture-hub."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import LoginRequired
from .routers import (
    admin,
    analytics,
    anthropic_compat,
    coding_agents,
    companion,
    conversations,
    extract,
    openai_compat,
    responses_compat,
    spa_api,
)
from .routers import (
    auth as auth_router,
)
from .settings import get_settings
from .storage.db import init_db

logger = logging.getLogger("prompture_hub")

try:
    __version__ = _pkg_version("prompture-hub")
except PackageNotFoundError:  # not installed (e.g. running from a raw checkout)
    __version__ = "0.0.0"


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
        version=__version__,
        lifespan=lifespan,
    )

    settings = get_settings()
    if settings.session_secret:
        app.add_middleware(
            SessionMiddleware,
            secret_key=settings.session_secret,
            session_cookie=settings.session_cookie_name,
            max_age=settings.session_max_age,
            same_site="lax",
            https_only=settings.base_url.startswith("https://"),
        )

    @app.exception_handler(LoginRequired)
    async def _login_required_handler(_request: Request, exc: LoginRequired):
        # The SPA renders its own login UI based on /api/me 401, so route
        # browser redirects there instead of a server-rendered page.
        target = exc.target if exc.target.startswith("/app") else "/app/"
        return RedirectResponse(url=target, status_code=302)

    # Programmatic surfaces — unchanged.
    app.include_router(openai_compat.router, prefix="/v1", tags=["openai-compat"])
    app.include_router(anthropic_compat.router, prefix="/v1", tags=["anthropic-compat"])
    app.include_router(responses_compat.router, prefix="/v1", tags=["openai-compat"])
    app.include_router(extract.router, prefix="/v1", tags=["prompture-native"])
    app.include_router(conversations.router, prefix="/v1", tags=["conversations"])
    app.include_router(coding_agents.router, prefix="/v1", tags=["coding-agents"])
    app.include_router(companion.router, prefix="/v1", tags=["companion"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])

    # Auth flow (OAuth redirects need server-side handling).
    app.include_router(auth_router.router, prefix="/auth", tags=["auth"])

    # SPA-backing JSON.
    app.include_router(spa_api.router, prefix="/api", tags=["spa"])
    app.include_router(analytics.router, prefix="/api", tags=["spa"])
    app.include_router(companion.dashboard_router, prefix="/api", tags=["spa"])

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    # StaticFiles raises RuntimeError at construction if the directory is
    # absent. The built SPA bundle (static/app/) is produced by `npm run build`
    # and is .gitignored, so a source checkout or a wheel published without the
    # frontend would otherwise crash on startup. Mount only when present; the
    # /app SPA handler below already degrades to a 503 when the bundle is missing.
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # --- SPA: served from /app/ ---
    spa_dir = os.path.join(static_dir, "app")
    spa_index = os.path.join(spa_dir, "index.html")
    spa_assets = os.path.join(spa_dir, "assets")
    if os.path.isdir(spa_assets):
        app.mount("/app/assets", StaticFiles(directory=spa_assets), name="spa-assets")

    @app.get("/")
    def root_to_app() -> RedirectResponse:
        return RedirectResponse(url="/app/", status_code=302)

    @app.get("/app")
    @app.get("/app/")
    @app.get("/app/{path:path}")
    def spa_index_handler(path: str = "") -> FileResponse:
        # Serve real files (favicon, vite.svg, etc.) when they exist,
        # otherwise fall back to index.html so client-side routes resolve.
        if path:
            candidate = os.path.normpath(os.path.join(spa_dir, path))
            if (
                candidate.startswith(spa_dir)
                and os.path.isfile(candidate)
                and not candidate.endswith("index.html")
            ):
                return FileResponse(candidate)
        if not os.path.isfile(spa_index):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "SPA bundle not built. Run `npm install && npm run build` "
                    "inside the `frontend/` directory."
                ),
            )
        return FileResponse(spa_index)

    return app


app = create_app()


def serve() -> None:
    """Run the hub with uvicorn using HUB_* settings."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "prompture_hub.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


def cli(argv: list[str] | None = None) -> None:
    """Console-script entry point.

    ``prompture-hub`` / ``prompture-hub serve`` runs the server;
    ``prompture-hub setup <tool>`` prints (or writes) client configuration.
    """
    import argparse
    import sys

    from .setup_tools import TOOLS, build_plan, create_setup_key, resolve_project_arg

    parser = argparse.ArgumentParser(prog="prompture-hub")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="Run the hub (default).")
    setup = sub.add_parser("setup", help="Point a coding tool or SDK at this hub.")
    setup.add_argument("tool", choices=sorted(TOOLS))
    setup.add_argument("--key", help="Hub key to use (default: a placeholder).")
    setup.add_argument("--create-key", action="store_true", help="Mint a new hub key named setup:<tool>.")
    setup.add_argument("--model", default="auto/balanced", help="Model, combo or alias the tool should use.")
    setup.add_argument("--small-model", default=None, help="Model for background/fast calls (default: --model).")
    setup.add_argument("--base-url", default=None, help="Hub URL (default: HUB_BASE_URL).")
    setup.add_argument("--write", action="store_true", help="Write the tool's config file where supported.")
    setup.add_argument(
        "--project",
        default=None,
        help="Attribute this tool's spend to a project (X-Project header). '.' uses the current folder name.",
    )

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command in (None, "serve"):
        serve()
        return

    key = args.key
    project = resolve_project_arg(args.project)
    if args.create_key:
        key = create_setup_key(args.tool, project)
        label = f"setup:{args.tool}:{project}" if project else f"setup:{args.tool}"
        print(f"# Created hub key '{label}' - shown once, store it now.\n")
    plan = build_plan(
        args.tool,
        base_url=args.base_url or get_settings().base_url,
        key=key,
        model=args.model,
        small_model=args.small_model,
        project=project,
    )
    print(plan.render())
    if args.write:
        if plan.writer is None:
            parser.exit(1, f"--write isn't supported for {args.tool}; copy the snippet above instead.\n")
        print(plan.writer())

"""Custom Hatchling build hook: build + bundle the Vite/React SPA into the wheel.

End users install prompture-hub from PyPI and run `prompture-hub` natively — they
must NOT need Node/npm. So the SPA (frontend/) is compiled to
`src/prompture_hub/static/app/` at *package build* time (sdist + wheel) and the
result is force-included into the distribution (see pyproject.toml).

Behaviour matrix:
  * Node/npm present                -> run `npm ci` (or `npm install`) + `npm run build`.
  * Node/npm absent, bundle present -> warn and skip (devs running `pip install -e .`,
                                       or a CI step that already built the SPA).
  * Node/npm absent, no bundle      -> fail loudly: the wheel would ship a broken UI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Paths are resolved relative to the project root (self.root).
FRONTEND_DIR = "frontend"
BUNDLE_REL = os.path.join("src", "prompture_hub", "static", "app")
BUNDLE_INDEX_REL = os.path.join(BUNDLE_REL, "index.html")


class SpaBuildHook(BuildHookInterface):
    """Compile the SPA before the sdist/wheel is assembled."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = self.root
        frontend_dir = os.path.join(root, FRONTEND_DIR)
        bundle_index = os.path.join(root, BUNDLE_INDEX_REL)

        has_prebuilt = os.path.isfile(bundle_index)
        npm = shutil.which("npm")

        if npm is None:
            if has_prebuilt:
                self._warn(
                    "npm not found on PATH; using the pre-built SPA bundle already "
                    f"present at {BUNDLE_REL}. Skipping frontend build."
                )
                return
            raise RuntimeError(
                "Cannot build prompture-hub: the SPA bundle is missing AND npm/Node "
                "is not installed.\n"
                f"Expected a pre-built bundle at {BUNDLE_INDEX_REL!r} or Node.js on PATH.\n"
                "Either install Node.js (https://nodejs.org) so this build hook can run "
                "`npm run build`, or build the SPA first with:\n"
                "    cd frontend && npm install && npm run build"
            )

        if not os.path.isdir(frontend_dir):
            if has_prebuilt:
                self._warn(
                    f"frontend/ directory not found but a pre-built bundle exists at "
                    f"{BUNDLE_REL}; skipping frontend build."
                )
                return
            raise RuntimeError(
                f"Cannot build the SPA: {FRONTEND_DIR!r} directory not found at {frontend_dir!r}."
            )

        # Install dependencies: prefer reproducible `npm ci` when a lockfile exists.
        lockfile = os.path.join(frontend_dir, "package-lock.json")
        if os.path.isfile(lockfile):
            install_cmd = [npm, "ci", "--no-audit", "--no-fund"]
        else:
            install_cmd = [npm, "install", "--no-audit", "--no-fund"]

        self._info(f"Installing frontend dependencies: {' '.join(install_cmd[1:])}")
        if self._run(install_cmd, cwd=frontend_dir) != 0:
            # `npm ci` is strict about lockfile sync; fall back to `npm install`.
            if install_cmd[1] == "ci":
                self._warn("`npm ci` failed; retrying with `npm install`.")
                if self._run(
                    [npm, "install", "--no-audit", "--no-fund"], cwd=frontend_dir
                ) != 0:
                    raise RuntimeError("npm install failed; cannot build the SPA.")
            else:
                raise RuntimeError("npm install failed; cannot build the SPA.")

        # `npm run build` is `tsc -b && vite build`. tsc's incremental cache
        # (tsconfig.tsbuildinfo) can go stale relative to a freshly installed
        # node_modules and make `tsc -b` a no-op or error. Drop it for a clean,
        # deterministic build (matters most for the from-sdist wheel build).
        tsbuildinfo = os.path.join(frontend_dir, "tsconfig.tsbuildinfo")
        if os.path.isfile(tsbuildinfo):
            try:
                os.remove(tsbuildinfo)
            except OSError:
                pass

        self._info("Building SPA: npm run build")
        if self._run([npm, "run", "build"], cwd=frontend_dir) != 0:
            raise RuntimeError("`npm run build` failed; cannot build the SPA.")

        if not os.path.isfile(bundle_index):
            raise RuntimeError(
                f"SPA build completed but {BUNDLE_INDEX_REL!r} was not produced. "
                "Check frontend/vite.config.ts build.outDir."
            )
        self._info(f"SPA bundle ready at {BUNDLE_REL}")

    # -- helpers ----------------------------------------------------------------

    def _run(self, cmd: list[str], cwd: str) -> int:
        # shell=False with a fully resolved npm path keeps this safe on Windows
        # (shutil.which resolves npm.cmd) and POSIX alike.
        proc = subprocess.run(cmd, cwd=cwd)  # noqa: S603
        return proc.returncode

    def _info(self, msg: str) -> None:
        # Hatchling captures app.display_*; fall back to stderr for plain builds.
        try:
            self.app.display_info(f"[prompture-hub:spa] {msg}")
        except Exception:
            print(f"[prompture-hub:spa] {msg}", file=sys.stderr)

    def _warn(self, msg: str) -> None:
        try:
            self.app.display_warning(f"[prompture-hub:spa] {msg}")
        except Exception:
            print(f"[prompture-hub:spa] WARNING: {msg}", file=sys.stderr)

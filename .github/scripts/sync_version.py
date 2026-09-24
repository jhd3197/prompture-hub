#!/usr/bin/env python3
"""Sync the release version into the repo's source files.

Run by ``.github/workflows/release.yml`` with the version computed from the
auto-bumped git tag, e.g.::

    python .github/scripts/sync_version.py 0.0.2

Updates, in place:
  * ``pyproject.toml`` -> ``version = "X.Y.Z"``
  * ``README.md``      -> the ``**vX.Y.Z**`` status line
  * ``VERSION``        -> ``X.Y.Z`` (single line; created if absent)

The app itself reads its version from package metadata at runtime, so there is
nothing to update in the Python source. Idempotent and safe to run locally.
Exits non-zero if pyproject's version line can't be found — a signal that the
file format changed and this script needs updating.
"""

from __future__ import annotations

import pathlib
import re
import sys

# Accepts plain semver plus optional pre-release / build metadata.
SEMVER = r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?"


def _replace(path: pathlib.Path, pattern: str, repl: str, *, required: bool) -> None:
    if not path.is_file():
        if required:
            sys.exit(f"{path}: file not found")
        return
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=1)
    if n == 0:
        if required:
            sys.exit(f"{path}: no version pattern matched; update sync_version.py")
        print(f"{path}: no version string found (skipped)")
        return
    if new != text:
        path.write_text(new, encoding="utf-8")
        print(f"{path}: set to {repl!r}")


def main(version: str) -> None:
    if not re.fullmatch(SEMVER, version):
        sys.exit(f"not a valid version: {version!r}")

    root = pathlib.Path(__file__).resolve().parents[2]

    _replace(
        root / "pyproject.toml",
        rf'(?m)^version = "{SEMVER}"$',
        f'version = "{version}"',
        required=True,
    )
    # README status line, e.g. "**v0.0.2** — solo / localhost / SQLite, ..."
    _replace(
        root / "README.md",
        rf"\*\*v{SEMVER}\*\*",
        f"**v{version}**",
        required=False,
    )
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    print(f"VERSION: {version}")
    print(f"synced version -> {version}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: sync_version.py X.Y.Z")
    main(sys.argv[1])

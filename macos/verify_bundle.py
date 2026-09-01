#!/usr/bin/env python3
"""Post-build smoke checks for dist/Cluny.app (run from repo root)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


REQUIRED_IMPORTS = (
    "cluny.app_mode",
    "cluny.brain_service",
    "cluny.brain_client",
    "cluny.api",
    "uvicorn",
    "fastapi",
    "httpx",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "chromadb",
)


def _bundle_python(app_path: Path) -> Path | None:
    """Return the embedded python executable inside Cluny.app, if present."""
    macos = app_path / "Contents" / "MacOS"
    if not macos.is_dir():
        return None
    for candidate in ("python", "Cluny"):
        p = macos / candidate
        if p.is_file():
            return p
    return None


def verify_imports() -> list[str]:
    errors: list[str] = []
    for mod in REQUIRED_IMPORTS:
        try:
            importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{mod}: {exc}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    app_path = root / "dist" / "Cluny.app"
    if not app_path.is_dir():
        print(f"Missing bundle: {app_path}", file=sys.stderr)
        return 1

    exe = _bundle_python(app_path)
    if exe:
        print(f"Bundle executable: {exe}")
    else:
        print("Warning: could not locate bundle executable", file=sys.stderr)

    size_mb = sum(f.stat().st_size for f in app_path.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"Bundle size: {size_mb:.1f} MB")

    errors = verify_imports()
    if errors:
        print("Import check failed:", file=sys.stderr)
        for line in errors:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("Bundle verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

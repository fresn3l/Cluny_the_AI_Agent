"""Packaged-app detection and default environment for Cluny.app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_SUPPORT_NAME = "Cluny"
DEFAULT_BRAIN_URL = "http://127.0.0.1:8787"


def is_packaged_app() -> bool:
    """True when running from a built .app or CLUNY_PACKAGED=1."""
    if os.environ.get("CLUNY_PACKAGED", "").strip() in ("1", "true", "yes"):
        return True
    exe = Path(sys.executable).as_posix()
    return "/Contents/MacOS/" in exe and ".app/" in exe


def app_support_dir() -> Path:
    """~/Library/Application Support/Cluny"""
    return Path.home() / "Library" / "Application Support" / APP_SUPPORT_NAME


def uses_http_brain() -> bool:
    """True when UI should talk to cluny serve over HTTP (packaged or CLUNY_USE_HTTP_BRAIN)."""
    if is_packaged_app():
        return True
    return os.environ.get("CLUNY_USE_HTTP_BRAIN", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def configure_app_environment() -> None:
    """
    Set defaults for Cluny.app before Settings.load().

    - Data dir → Application Support (packaged only, unless CLUNY_DATA_DIR set)
    - Brain URL → local serve (packaged or CLUNY_USE_HTTP_BRAIN=1)
    """
    if is_packaged_app():
        os.environ.setdefault("CLUNY_PACKAGED", "1")
        support = app_support_dir()
        support.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("CLUNY_DATA_DIR", str(support))

    if uses_http_brain():
        os.environ.setdefault("CLUNY_BRAIN_URL", DEFAULT_BRAIN_URL)

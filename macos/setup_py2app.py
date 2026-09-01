"""
py2app build script for Cluny menu bar app.

Usage (from repo root):
  python macos/setup_py2app.py py2app
  # or: ./macos/build_py2app.sh
"""

from __future__ import annotations

import sys
from pathlib import Path

from setuptools import setup

_MACOS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_MACOS_DIR))
from py2app_options import APP_NAME, PY2APP_OPTIONS  # noqa: E402

APP = ["cluny/app_entry.py"]

setup(
    name=APP_NAME,
    app=APP,
    options={"py2app": PY2APP_OPTIONS},
    setup_requires=["py2app"],
)

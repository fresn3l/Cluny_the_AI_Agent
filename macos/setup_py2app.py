"""
py2app build script for Cluny menu bar app.

Usage (from repo root):
  python macos/setup_py2app.py py2app
  # or: ./macos/build_py2app.sh
"""

from __future__ import annotations

from setuptools import setup

APP = ["cluny/app_entry.py"]
APP_NAME = "Cluny"

OPTIONS = {
    "argv_emulation": False,
    "packages": [
        "cluny",
        "fastapi",
        "uvicorn",
        "httpx",
        "pydantic",
        "chromadb",
        "PySide6",
    ],
    "includes": [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.cluny.app",
        "CFBundleVersion": "0.2.0",
        "CFBundleShortVersionString": "0.2.0",
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
    "resources": [],
}

setup(
    name=APP_NAME,
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)

"""Shared py2app bundle options (imported by setup_py2app.py and tests)."""

from __future__ import annotations

APP_NAME = "Cluny"
BUNDLE_VERSION = "0.2.0"

# Packages copied into the .app; keep lean but include HTTP brain + Qt UI deps.
PY2APP_PACKAGES = [
    "cluny",
    "fastapi",
    "starlette",
    "uvicorn",
    "httpx",
    "httpcore",
    "h11",
    "anyio",
    "sniffio",
    "pydantic",
    "pydantic_core",
    "chromadb",
    "PySide6",
    "shiboken6",
    "sqlite3",
    "yaml",
    "dateutil",
    "trafilatura",
    "pypdf",
    "fitz",
    "PIL",
]

# Uvicorn/FastAPI submodules that py2app often misses on a clean Mac.
PY2APP_INCLUDES = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "email.mime.multipart",
    "email.mime.text",
    "multipart",
    "encodings.idna",
]

# Qt plugin folders required for menu bar + full window on macOS.
PY2APP_QT_PLUGINS = [
    "platforms",
    "styles",
    "imageformats",
]

# Trim obvious dead weight from the bundle when possible.
PY2APP_EXCLUDES = [
    "tkinter",
    "matplotlib",
    "numpy.distutils",
    "scipy",
    "pandas",
    "IPython",
    "notebook",
    "pytest",
    "test",
    "unittest",
]

PY2APP_OPTIONS = {
    "argv_emulation": False,
    "packages": PY2APP_PACKAGES,
    "includes": PY2APP_INCLUDES,
    "excludes": PY2APP_EXCLUDES,
    "qt_plugins": PY2APP_QT_PLUGINS,
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.cluny.app",
        "CFBundleVersion": BUNDLE_VERSION,
        "CFBundleShortVersionString": BUNDLE_VERSION,
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
    },
    "resources": [],
}

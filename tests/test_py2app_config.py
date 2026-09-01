"""Tests for py2app bundle configuration."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_py2app_options():
    path = Path(__file__).resolve().parents[1] / "macos" / "py2app_options.py"
    spec = importlib.util.spec_from_file_location("py2app_options", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_py2app_includes_qt_plugins():
    opts = _load_py2app_options()
    assert "platforms" in opts.PY2APP_QT_PLUGINS
    assert "styles" in opts.PY2APP_QT_PLUGINS


def test_py2app_includes_uvicorn_submodules():
    opts = _load_py2app_options()
    joined = " ".join(opts.PY2APP_INCLUDES)
    assert "uvicorn.lifespan.on" in joined
    assert "uvicorn.protocols.http.auto" in joined


def test_py2app_core_packages():
    opts = _load_py2app_options()
    for pkg in ("cluny", "fastapi", "uvicorn", "PySide6", "chromadb", "httpx"):
        assert pkg in opts.PY2APP_PACKAGES


def test_verify_bundle_lists_critical_imports():
    path = Path(__file__).resolve().parents[1] / "macos" / "verify_bundle.py"
    text = path.read_text(encoding="utf-8")
    for mod in ("cluny.api", "uvicorn", "PySide6.QtWidgets", "chromadb"):
        assert mod in text

"""Tests for packaged app mode helpers."""

from __future__ import annotations

import os

from cluny.app_mode import DEFAULT_BRAIN_URL, app_support_dir, configure_app_environment, is_packaged_app


def test_app_support_dir():
    p = app_support_dir()
    assert p.name == "Cluny"
    assert "Application Support" in str(p)


def test_is_packaged_env_flag(monkeypatch):
    monkeypatch.setenv("CLUNY_PACKAGED", "1")
    assert is_packaged_app() is True


def test_configure_sets_brain_url_when_packaged(monkeypatch, tmp_path):
    monkeypatch.setenv("CLUNY_PACKAGED", "1")
    monkeypatch.delenv("CLUNY_BRAIN_URL", raising=False)
    monkeypatch.delenv("CLUNY_DATA_DIR", raising=False)
    monkeypatch.setattr("cluny.app_mode.app_support_dir", lambda: tmp_path / "support")
    configure_app_environment()
    assert os.environ.get("CLUNY_BRAIN_URL") == DEFAULT_BRAIN_URL
    assert "support" in os.environ.get("CLUNY_DATA_DIR", "")


def test_configure_http_brain_flag(monkeypatch):
    monkeypatch.delenv("CLUNY_PACKAGED", raising=False)
    monkeypatch.delenv("CLUNY_BRAIN_URL", raising=False)
    monkeypatch.setenv("CLUNY_USE_HTTP_BRAIN", "1")
    configure_app_environment()
    assert os.environ.get("CLUNY_BRAIN_URL") == DEFAULT_BRAIN_URL

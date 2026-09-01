"""Tests for DMG packaging script."""

from __future__ import annotations

from pathlib import Path


def test_create_dmg_script_exists_and_references_app():
    path = Path(__file__).resolve().parents[1] / "macos" / "create_dmg.sh"
    text = path.read_text(encoding="utf-8")
    assert "dist/Cluny.app" in text
    assert "hdiutil create" in text
    assert "Applications" in text

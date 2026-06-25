"""Tests for backup helpers."""

from __future__ import annotations

from cluny.backup import export_data, run_scheduled_backup


def test_scheduled_backup(settings):
    path = run_scheduled_backup(settings, include_files=False)
    assert path.is_file()
    assert path.name.startswith("cluny-")
    assert path.suffix == ".zip"


def test_export_plain_zip(settings, tmp_path):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.catalog_root.mkdir(parents=True, exist_ok=True)
    sqlite = settings.catalog_root / settings.library_sqlite_name
    sqlite.write_text("x", encoding="utf-8")
    out = tmp_path / "out.zip"
    result = export_data(out, settings, include_files=False)
    assert result.is_file()

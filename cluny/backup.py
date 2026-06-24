"""Export and restore Cluny data directory snapshots."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from cluny.config import Settings


def export_data(
    out_path: Path,
    settings: Settings,
    *,
    include_files: bool = True,
) -> Path:
    """
    Create a zip archive of library.sqlite, chroma/, and optional managed files/.
    Returns the path to the created archive.
    """
    out = out_path.expanduser().resolve()
    if out.suffix != ".zip":
        out = out.with_suffix(".zip")

    data_dir = settings.data_dir
    catalog = settings.catalog_root
    sqlite = catalog / settings.library_sqlite_name
    chroma = data_dir / "chroma"
    files_dir = catalog / "files"

    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if sqlite.is_file():
            zf.write(sqlite, arcname=f"library/{settings.library_sqlite_name}")
        if chroma.is_dir():
            for f in chroma.rglob("*"):
                if f.is_file():
                    zf.write(f, arcname=str(Path("chroma") / f.relative_to(chroma)))
        if include_files and files_dir.is_dir():
            for f in files_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, arcname=str(Path("library/files") / f.relative_to(files_dir)))

        manifest = (
            f"CLUNY_DATA_DIR={data_dir}\n"
            f"CLUNY_CATALOG_DIR={settings.catalog_dir_name}\n"
            f"CLUNY_LIBRARY_SQLITE={settings.library_sqlite_name}\n"
        )
        zf.writestr("MANIFEST.txt", manifest)

    return out


def restore_data(
    archive_path: Path,
    settings: Settings,
    *,
    merge: bool = False,
) -> None:
    """
    Extract a Cluny export zip into the configured data directory.
    If merge=False, existing chroma/ and library sqlite are replaced.
    """
    archive = archive_path.expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Archive not found: {archive}")

    data_dir = settings.data_dir
    catalog = settings.catalog_root
    if not merge:
        chroma = data_dir / "chroma"
        if chroma.is_dir():
            shutil.rmtree(chroma)
        sqlite = catalog / settings.library_sqlite_name
        if sqlite.is_file():
            sqlite.unlink()

    data_dir.mkdir(parents=True, exist_ok=True)
    catalog.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(data_dir)

"""Install macOS LaunchAgent for cluny serve."""

from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path

from cluny.config import find_repo_root

LABEL = "com.cluny.serve"
AGENT_NAME = f"{LABEL}.plist"


def _run_cluny_sh() -> Path:
    root = find_repo_root()
    if root is None:
        raise RuntimeError("Could not find repo root (pyproject.toml).")
    script = root / "run_cluny.sh"
    if not script.is_file():
        raise FileNotFoundError(f"Missing launcher: {script}")
    return script.resolve()


def _agent_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _installed_plist() -> Path:
    return _agent_dir() / AGENT_NAME


def install_launch_agent(*, force: bool = False) -> Path:
    """Write LaunchAgent plist and load it. Returns path to installed plist."""
    script = _run_cluny_sh()
    root = find_repo_root()
    template = root / "macos" / AGENT_NAME if root else None
    dest = _installed_plist()
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        raise FileExistsError(
            f"LaunchAgent already installed at {dest}. Use --force to replace."
        )

    if template and template.is_file():
        data = plistlib.loads(template.read_bytes())
    else:
        data = {
            "Label": LABEL,
            "ProgramArguments": [str(script), "serve"],
            "RunAtLoad": True,
            "KeepAlive": False,
            "StandardOutPath": "/tmp/cluny-serve.log",
            "StandardErrorPath": "/tmp/cluny-serve.err",
        }

    data["ProgramArguments"] = [str(script), "serve"]
    dest.write_bytes(plistlib.dumps(data))

    subprocess.run(["launchctl", "bootout", f"gui/{_gui_uid()}", str(dest)], check=False)
    subprocess.run(["launchctl", "bootstrap", f"gui/{_gui_uid()}", str(dest)], check=True)
    return dest


def uninstall_launch_agent() -> bool:
    """Unload and remove LaunchAgent. Returns True if something was removed."""
    dest = _installed_plist()
    if not dest.exists():
        return False
    subprocess.run(["launchctl", "bootout", f"gui/{_gui_uid()}", str(dest)], check=False)
    dest.unlink()
    return True


def launch_agent_status() -> dict[str, str | bool]:
    dest = _installed_plist()
    return {
        "installed": dest.is_file(),
        "path": str(dest),
        "script": str(_run_cluny_sh()) if find_repo_root() else "",
    }


def _gui_uid() -> int:
    import os

    return os.getuid()

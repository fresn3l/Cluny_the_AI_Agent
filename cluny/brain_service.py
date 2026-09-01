"""Ensure local cluny serve is running for HTTP-first UI clients."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass

import httpx

from cluny.app_mode import DEFAULT_BRAIN_URL
from cluny.config import Settings

_SERVE_PROC: subprocess.Popen[str] | None = None


@dataclass(frozen=True)
class BrainHealth:
    ok: bool
    brain_ready: bool
    message: str | None
    ollama_ok: bool


def brain_base_url(settings: Settings) -> str:
    raw = settings.brain_url or DEFAULT_BRAIN_URL
    return raw.rstrip("/")


def fetch_brain_health(settings: Settings | None = None, *, timeout: float = 3.0) -> BrainHealth:
    settings = settings or Settings.load()
    url = f"{brain_base_url(settings)}/health"
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:  # noqa: BLE001
        return BrainHealth(
            ok=False,
            brain_ready=False,
            message=str(exc),
            ollama_ok=False,
        )
    return BrainHealth(
        ok=True,
        brain_ready=bool(data.get("brain_ready", data.get("ollama_ok", False))),
        message=data.get("message"),
        ollama_ok=bool(data.get("ollama_ok", False)),
    )


def _spawn_serve(settings: Settings) -> subprocess.Popen[str]:
    """Start uvicorn in a child process (dev repo or packaged interpreter)."""
    global _SERVE_PROC
    if _SERVE_PROC is not None and _SERVE_PROC.poll() is None:
        return _SERVE_PROC

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "cluny.api:create_app",
        "--factory",
        "--host",
        settings.api_bind_host,
        "--port",
        str(settings.api_port),
        "--log-level",
        "warning",
    ]
    env = {**os.environ, "CLUNY_DATA_DIR": str(settings.data_dir)}
    _SERVE_PROC = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    return _SERVE_PROC


def ensure_brain_running(
    settings: Settings | None = None,
    *,
    start_timeout_sec: float = 15.0,
    spawn_if_down: bool = True,
) -> BrainHealth:
    """
    Probe /health; optionally spawn cluny serve and wait until reachable.

    No-op when CLUNY_BRAIN_URL is empty (in-process dev mode).
    """
    settings = settings or Settings.load()
    if not settings.brain_url:
        return BrainHealth(ok=True, brain_ready=True, message=None, ollama_ok=True)

    health = fetch_brain_health(settings)
    if health.ok:
        return health
    if not spawn_if_down:
        return health

    try:
        _spawn_serve(settings)
    except Exception as exc:  # noqa: BLE001
        return BrainHealth(ok=False, brain_ready=False, message=str(exc), ollama_ok=False)

    deadline = time.monotonic() + start_timeout_sec
    while time.monotonic() < deadline:
        time.sleep(0.25)
        health = fetch_brain_health(settings)
        if health.ok:
            return health

    return BrainHealth(
        ok=False,
        brain_ready=False,
        message="Brain service did not start in time. Try: cluny serve",
        ollama_ok=False,
    )


def stop_spawned_serve() -> None:
    """Terminate serve process started by this process (e.g. on app quit)."""
    global _SERVE_PROC
    if _SERVE_PROC is None:
        return
    if _SERVE_PROC.poll() is None:
        _SERVE_PROC.terminate()
        try:
            _SERVE_PROC.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _SERVE_PROC.kill()
    _SERVE_PROC = None

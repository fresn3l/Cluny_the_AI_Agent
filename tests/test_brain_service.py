"""Tests for brain service health and spawn helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cluny.brain_service import ensure_brain_running, fetch_brain_health, stop_spawned_serve


def test_fetch_brain_health_ok(settings, monkeypatch):
    monkeypatch.setenv("CLUNY_BRAIN_URL", "http://127.0.0.1:8787")

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"brain_ready": True, "ollama_ok": True, "message": None}

    with patch("cluny.brain_service.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = FakeResp()
        health = fetch_brain_health(settings)
    assert health.ok is True
    assert health.brain_ready is True


def test_ensure_brain_noop_without_brain_url(settings, monkeypatch):
    monkeypatch.setenv("CLUNY_BRAIN_URL", "")
    health = ensure_brain_running(settings, spawn_if_down=False)
    assert health.brain_ready is True


def test_ensure_brain_spawns_when_down(settings, monkeypatch):
    monkeypatch.setenv("CLUNY_BRAIN_URL", "http://127.0.0.1:8787")
    calls = {"n": 0}

    def fake_health(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            from cluny.brain_service import BrainHealth

            return BrainHealth(ok=False, brain_ready=False, message="down", ollama_ok=False)
        from cluny.brain_service import BrainHealth

        return BrainHealth(ok=True, brain_ready=True, message=None, ollama_ok=True)

    with (
        patch("cluny.brain_service.fetch_brain_health", side_effect=fake_health),
        patch("cluny.brain_service._spawn_serve", return_value=MagicMock()),
        patch("cluny.brain_service.time.sleep"),
    ):
        health = ensure_brain_running(settings)
    assert health.ok is True
    stop_spawned_serve()

"""Tests for brain config HTTP API (Sprint 16 Phase B)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.brain_config import invalidate_brain_config_cache, load_brain_config
from cluny.config import Settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    invalidate_brain_config_cache()
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_brain_config_cache()
    yield
    invalidate_brain_config_cache()


def test_brain_config_get_defaults(client: TestClient):
    r = client.get("/brain/config")
    assert r.status_code == 200
    data = r.json()
    assert "defaults" in data
    assert "prompts" in data
    assert "rag_system" in data["defaults"]


def test_brain_config_put_persona(client: TestClient, tmp_path):
    r = client.put(
        "/brain/config",
        json={"global_persona": "You are a concise assistant."},
    )
    assert r.status_code == 200
    assert r.json()["global_persona"] == "You are a concise assistant."
    saved = json.loads(
        (tmp_path / ".cluny" / "brain_config.json").read_text(encoding="utf-8")
    )
    assert saved["global_persona"] == "You are a concise assistant."


def test_brain_config_put_prompt_override(client: TestClient, tmp_path):
    r = client.put(
        "/brain/config",
        json={"prompts": {"rag_system": "Custom RAG prompt."}},
    )
    assert r.status_code == 200
    assert "Custom RAG prompt." in r.json()["prompts"]["rag_system"]
    saved = json.loads(
        (tmp_path / ".cluny" / "brain_config.json").read_text(encoding="utf-8")
    )
    assert saved["prompts"]["rag_system"] == "Custom RAG prompt."


def test_brain_config_put_invalid_prompt_key(client: TestClient):
    r = client.put(
        "/brain/config",
        json={"prompts": {"not_a_real_key": "x"}},
    )
    assert r.status_code == 400


def test_brain_config_reset_all(client: TestClient, tmp_path):
    client.put("/brain/config", json={"global_persona": "Test"})
    r = client.post("/brain/config/reset", json={"reset_all": True})
    assert r.status_code == 200
    assert r.json()["global_persona"] == ""
    cfg = load_brain_config(Settings.load())
    assert cfg.global_persona == ""


def test_brain_config_reset_single_prompt(client: TestClient):
    client.put("/brain/config", json={"prompts": {"propose_system": "Custom propose."}})
    r = client.post(
        "/brain/config/reset",
        json={"prompt_key": "propose_system"},
    )
    assert r.status_code == 200
    assert r.json()["overrides"]["propose_system"] is None

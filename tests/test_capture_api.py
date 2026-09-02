"""Tests for POST /capture API."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.capture import CaptureResult


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    return TestClient(create_app())


def test_capture_empty_text(client: TestClient):
    r = client.post("/capture", json={"text": "   "})
    assert r.status_code == 400


def test_capture_success(client: TestClient):
    fake = CaptureResult(
        doc_id="doc1",
        chunk_count=1,
        title="2026-09-02 capture",
        unchanged=False,
        source="telegram-capture",
        collection="capture",
    )
    with patch("cluny.api.capture_note", return_value=fake):
        r = client.post("/capture", json={"text": "Quick note from phone"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["doc_id"] == "doc1"
    assert data["chunk_count"] == 1

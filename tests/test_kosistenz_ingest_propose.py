"""Tests for ingest collection assignment and RAG-backed propose API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.documents import IndexResult
from cluny.proposals import WorkProposal


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    return TestClient(create_app())


def test_ingest_text_with_collection(client: TestClient):
    with patch("cluny.api.add_inline_text") as mock_add:
        mock_add.return_value = IndexResult(doc_id="doc1", chunk_count=2, unchanged=False)
        r = client.post(
            "/ingest/text",
            json={
                "text": "Weekly analytics\nTasks completed: 12",
                "catalog": True,
                "source": "kosistenz-analytics",
                "title": "analytics-2026-W35",
                "collection": "analytics",
            },
        )
    assert r.status_code == 200
    assert r.json()["chunk_count"] == 2
    mock_add.assert_called_once()
    assert mock_add.call_args.kwargs["collection_name"] == "analytics"


def test_propose_with_collection_and_analytics(client: TestClient):
    with patch(
        "cluny.api.run_proposals",
        return_value=[WorkProposal(title="Reflect on slips", estimate_minutes=20, due=None, keywords=[])],
    ) as mock_run:
        r = client.post(
            "/propose",
            json={
                "question": "What should I change?",
                "collection": "journal",
                "context_json": {
                    "analytics": {
                        "period": "2026-W35",
                        "tasks_slipped": 3,
                    }
                },
            },
        )
    assert r.status_code == 200
    assert r.json()["proposals"][0]["title"] == "Reflect on slips"
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["collection"] == "journal"

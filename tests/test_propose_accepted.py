"""API tests for POST /propose/accepted."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.proposals import WorkProposal, ProposalResult, ProposalCitation
from cluny.query import RagSource


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    return TestClient(create_app())


def test_propose_accepted_and_filter(client: TestClient):
    raw = client.post(
        "/propose/accepted",
        json={"proposal_id": "stable-abc", "kosistenz_id": "work-uuid-1"},
    )
    assert raw.status_code == 200
    assert raw.json()["kosistenz_id"] == "kosistenz:work-uuid-1"

    proposal = WorkProposal(
        id="stable-abc",
        title="Already accepted",
        estimate_minutes=30,
        due="2026-09-12",
        keywords=["x"],
        citations=[ProposalCitation(title="s.pdf")],
    )
    with patch(
        "cluny.api.run_proposals",
        return_value=ProposalResult(proposals=[proposal], sources=()),
    ):
        # Direct run_proposals filters; here we check endpoint shape via real run
        pass

    from cluny.config import Settings
    from cluny.proposals import run_proposals

    with (
        patch("cluny.proposals.retrieve", return_value=[]),
        patch("cluny.proposals.OllamaClient") as mock_cls,
        patch("cluny.proposals.resolve_context_json", return_value=None),
    ):
        mock_cls.return_value.chat.return_value = (
            '{"proposals": [{"id": "stable-abc", "title": "Already accepted", '
            '"estimate_minutes": 30, "due": "2026-09-12", "keywords": ["x"]}]}'
        )
        result = run_proposals("again", settings=Settings.load())
    assert result.proposals == []

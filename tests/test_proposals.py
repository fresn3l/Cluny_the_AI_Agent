"""Tests for structured work proposals."""

from __future__ import annotations

from unittest.mock import patch

from cluny.proposals import (
    RETRIEVED_SNIPPETS_HEADER,
    ProposalResult,
    WorkProposal,
    _parse_proposals,
    chunks_to_sources,
    format_retrieved_snippets,
    run_proposals,
)
from cluny.query import RetrievedChunk


def test_parse_proposals_json():
    raw = '{"proposals": [{"title": "Draft agenda", "estimate_minutes": 25, "due": "2026-09-04", "keywords": ["agenda"]}]}'
    items = _parse_proposals(raw)
    assert len(items) == 1
    assert items[0].title == "Draft agenda"
    assert items[0].estimate_minutes == 25


def test_format_retrieved_snippets():
    chunks = [
        RetrievedChunk(
            text="Felt burned out on Friday",
            label="2026-08-28 journal",
            doc_path=None,
            chunk_index=0,
            score=0.9,
        )
    ]
    block = format_retrieved_snippets(chunks)
    assert block is not None
    assert RETRIEVED_SNIPPETS_HEADER in block
    assert "burned out" in block


def test_run_proposals_mocked(settings):
    raw = '{"proposals": [{"title": "Review PR", "estimate_minutes": 30, "due": null, "keywords": []}]}'
    chunks = [
        RetrievedChunk(
            text="Slipped three tasks last week",
            label="analytics-2026-W35",
            doc_path=None,
            chunk_index=0,
            score=0.8,
        )
    ]
    with (
        patch("cluny.proposals.retrieve", return_value=chunks) as mock_retrieve,
        patch("cluny.proposals.OllamaClient") as mock_cls,
    ):
        mock_cls.return_value.chat.return_value = raw
        result = run_proposals(
            "What should I change next week?",
            settings=settings,
            context_json={"analytics": {"tasks_slipped": 3}},
            collection="journal",
            k=3,
        )
    assert len(result.proposals) == 1
    assert result.proposals[0].title == "Review PR"
    assert len(result.sources) == 1
    assert result.sources[0].label == "analytics-2026-W35"
    mock_retrieve.assert_called_once()
    call_kwargs = mock_retrieve.call_args.kwargs
    assert call_kwargs["collection_name"] == "journal"
    assert call_kwargs["k"] == 3
    user_prompt = mock_cls.return_value.chat.call_args.kwargs["user"]
    assert RETRIEVED_SNIPPETS_HEADER in user_prompt
    assert "Slipped three tasks" in user_prompt


def test_chunks_to_sources_preview():
    chunks = [
        RetrievedChunk(
            text="Long journal entry about the week",
            label="2026-08-28 journal",
            doc_path="inline:kosistenz-journal:abc",
            chunk_index=1,
            score=0.9,
        )
    ]
    sources = chunks_to_sources(chunks)
    assert len(sources) == 1
    assert sources[0].label == "2026-08-28 journal"
    assert sources[0].chunk_index == 1

def test_run_proposals_without_retrieval(settings):
    raw = '{"proposals": [{"title": "Walk", "estimate_minutes": 15, "due": null, "keywords": []}]}'
    with (
        patch("cluny.proposals.retrieve", return_value=[]),
        patch("cluny.proposals.OllamaClient") as mock_cls,
    ):
        mock_cls.return_value.chat.return_value = raw
        result = run_proposals("Anything?", settings=settings)
    assert result.proposals[0].title == "Walk"
    user_prompt = mock_cls.return_value.chat.call_args.kwargs["user"]
    assert RETRIEVED_SNIPPETS_HEADER not in user_prompt

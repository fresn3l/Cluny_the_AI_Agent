"""Tests for proposals: stable ids, day-only dues, accept pointers."""

from __future__ import annotations

from unittest.mock import patch

from cluny.proposal_accepts import accepted_proposal_ids, record_acceptance
from cluny.proposals import (
    RETRIEVED_SNIPPETS_HEADER,
    _parse_proposals,
    chunks_to_sources,
    format_retrieved_snippets,
    normalize_due,
    run_proposals,
    stable_proposal_id,
)
from cluny.query import RetrievedChunk
from cluny.tools.proposals import _create_proposal, clear_agent_proposals, last_agent_proposals
from cluny.tasks_db import connect as tasks_connect


def test_normalize_due_strips_times():
    assert normalize_due("2026-09-12") == "2026-09-12"
    assert normalize_due("2026-09-12T14:30:00") == "2026-09-12"
    assert normalize_due("2026-09-12 14:30") == "2026-09-12"
    assert normalize_due("Friday at 14:30") is None
    assert normalize_due(None) is None


def test_stable_proposal_id_consistent():
    a = stable_proposal_id(title="Essay", due="2026-09-12", keywords=["spanish"])
    b = stable_proposal_id(title="Essay", due="2026-09-12", keywords=["spanish"])
    c = stable_proposal_id(title="Essay", due="2026-09-13", keywords=["spanish"])
    assert a == b
    assert a != c


def test_parse_proposals_json_ids_and_citations():
    raw = (
        '{"proposals": [{"id": "abc123", "title": "Draft agenda", '
        '"estimate_minutes": 25, "due": "2026-09-04 14:30", '
        '"keywords": ["agenda"], '
        '"citations": [{"title": "syllabus.pdf", "locator": "p3"}]}]}'
    )
    items = _parse_proposals(raw)
    assert len(items) == 1
    assert items[0].title == "Draft agenda"
    assert items[0].due == "2026-09-04"
    assert items[0].id == "abc123"
    assert items[0].citations[0].title == "syllabus.pdf"
    d = items[0].to_dict()
    assert "id" in d and "citations" in d


def test_identical_parse_yields_same_hash_id():
    raw = (
        '{"proposals": [{"title": "Review PR", "estimate_minutes": 30, '
        '"due": "2026-09-10", "keywords": ["code"]}]}'
    )
    a = _parse_proposals(raw)
    b = _parse_proposals(raw)
    assert a[0].id == b[0].id


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


def test_run_proposals_mocked(settings):
    raw = (
        '{"proposals": [{"title": "Review PR", "estimate_minutes": 30, '
        '"due": "2026-09-10", "keywords": ["code"]}]}'
    )
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
        patch("cluny.proposals.retrieve", return_value=chunks),
        patch("cluny.proposals.OllamaClient") as mock_cls,
        patch("cluny.proposals.resolve_context_json", return_value={"date": "2026-09-09"}),
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
    assert result.proposals[0].due == "2026-09-10"
    assert result.proposals[0].id
    assert result.proposals[0].citations


def test_accept_suppresses_repropose(settings):
    raw = (
        '{"proposals": [{"title": "Syllabus essay", "estimate_minutes": 45, '
        '"due": "2026-09-12", "keywords": ["spanish"]}]}'
    )
    items = _parse_proposals(raw)
    pid = items[0].id
    record_acceptance(settings, proposal_id=pid, kosistenz_id="kosistenz:work-1")
    assert pid in accepted_proposal_ids(settings)

    chunks: list[RetrievedChunk] = []
    with (
        patch("cluny.proposals.retrieve", return_value=chunks),
        patch("cluny.proposals.OllamaClient") as mock_cls,
        patch("cluny.proposals.resolve_context_json", return_value=None),
    ):
        mock_cls.return_value.chat.return_value = raw
        result = run_proposals("Again?", settings=settings)
    assert all(p.id != pid for p in result.proposals)
    assert result.proposals == []


def test_create_proposal_tool_does_not_write_tasks(settings):
    clear_agent_proposals()
    conn = tasks_connect(settings)
    before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()
    out = _create_proposal(
        {
            "title": "From tool",
            "due": "2026-09-12T14:30:00",
            "keywords": ["x"],
        },
        settings,
    )
    assert out["due"] == "2026-09-12"
    assert out["id"]
    assert last_agent_proposals()
    conn = tasks_connect(settings)
    after = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()
    assert after == before


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
    assert sources[0].chunk_index == 1

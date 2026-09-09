"""Journal ingest metadata from Kosistenz header lines."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cluny.documents import IndexResult, add_inline_text, parse_kosistenz_ingest_headers


def test_parse_morning_brief_headers():
    text = (
        "kind=morning_brief\n"
        "slot=morning\n"
        "focus=a,b\n"
        "\n"
        "Body of the brief."
    )
    meta, body = parse_kosistenz_ingest_headers(text)
    assert meta["kind"] == "morning_brief"
    assert meta["slot"] == "morning"
    assert "focus" in meta
    assert "Body of the brief" in body


def test_parse_evening_rolled_does_not_invent_tasks():
    text = "kind=evening_review\nrolled=uuid-1,uuid-2\n\nLeftovers noted."
    meta, _body = parse_kosistenz_ingest_headers(text)
    assert meta["kind"] == "evening_review"
    assert "rolled" in meta
    # Parsing alone must not touch tasks — no create_task import side effect.


def test_add_inline_text_keeps_kind_metadata(settings):
    text = "kind=morning_brief\nslot=morning\n\nShip the pack."
    chroma = MagicMock()
    ollama = MagicMock()
    with patch(
        "cluny.documents.ingest_string",
        return_value=(1, ["kind=morning_brief\nslot=morning\n\nShip the pack."]),
    ) as mock_ingest:
        result = add_inline_text(
            settings,
            chroma,
            ollama,
            text,
            source_label="kosistenz-journal",
            title="2026-09-09 morning_brief",
            collection_name="journal",
        )
    assert isinstance(result, IndexResult)
    assert result.chunk_count == 1
    kwargs = mock_ingest.call_args.kwargs
    extra = kwargs.get("extra_metadata") or {}
    assert extra.get("kind") == "morning_brief"
    assert extra.get("slot") == "morning"

"""Tests for Sprint 6 features."""

from __future__ import annotations

from pathlib import Path

from cluny.calendar_db import import_ics, connect as cal_connect, list_upcoming
from cluny.config import Settings
from cluny.library_db import (
    add_doc_to_collection,
    connect,
    create_collection,
    doc_ids_in_collection,
    duplicate_hash_groups,
    upsert_document,
)
from cluny.supervisor import classify_intent


def test_collections(settings: Settings):
    conn = connect(settings)
    create_collection(conn, "research")
    upsert_document(conn, "d1", "/a.md", "md", "A", "h1", 1, 1)
    add_doc_to_collection(conn, "d1", "research")
    ids = doc_ids_in_collection(conn, "research")
    conn.close()
    assert "d1" in ids


def test_duplicate_hash_report(settings: Settings):
    conn = connect(settings)
    upsert_document(conn, "d1", "/a.md", "md", "A", "same", 1, 1)
    upsert_document(conn, "d2", "/b.md", "md", "B", "same", 1, 1)
    groups = duplicate_hash_groups(conn)
    conn.close()
    assert "same" in groups
    assert len(groups["same"]) == 2


def test_supervisor_routing(settings: Settings):
    assert classify_intent("What's due this week?", settings) == "tasks_agent"
    assert classify_intent("What did Smith say in my notes?", settings) == "knowledge_agent"
    assert classify_intent("What's on my calendar tomorrow?", settings) == "calendar"
    assert (
        classify_intent("Summarize Smith notes and add a task to email him", settings)
        == "planner"
    )


def test_ics_import(settings: Settings, tmp_path: Path):
    ics = tmp_path / "cal.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Team sync\nDTSTART:20260625T100000Z\nEND:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    n = import_ics(ics, settings)
    assert n == 1
    conn = cal_connect(settings)
    events = list_upcoming(conn)
    conn.close()
    assert events[0].summary == "Team sync"

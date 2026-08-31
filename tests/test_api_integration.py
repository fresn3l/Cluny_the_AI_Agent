"""Integration API tests for Kosistenz consumers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app
from cluny.config import Settings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    monkeypatch.setenv("CLUNY_SUPERVISOR", "regex")
    return TestClient(create_app())


@pytest.fixture
def settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    return Settings.load()


def test_health_extended(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "ollama_ok" in data
    assert "doc_count" in data
    assert "task_count" in data


def test_task_crud(client: TestClient):
    r = client.post(
        "/tasks",
        json={
            "title": "Kosistenz task",
            "due_at": "tomorrow",
            "external_id": "kosistenz:test-001",
        },
    )
    assert r.status_code == 200
    task = r.json()
    assert task["title"] == "Kosistenz task"
    assert task["external_id"] == "kosistenz:test-001"
    tid = task["id"]

    r2 = client.get("/tasks", params={"external_id": "kosistenz:test-001"})
    assert r2.status_code == 200
    assert len(r2.json()["tasks"]) == 1

    r3 = client.patch(f"/tasks/{tid}", json={"notes": "updated"})
    assert r3.status_code == 200
    assert r3.json()["notes"] == "updated"

    r4 = client.post(f"/tasks/{tid}/complete")
    assert r4.status_code == 200
    assert r4.json()["status"] == "done"

    r5 = client.delete(f"/tasks/{tid}")
    assert r5.status_code == 200


def test_context_day(client: TestClient):
    client.post("/tasks", json={"title": "Day task", "due_at": "today"})
    r = client.post("/context/day", json={"date": "today"})
    assert r.status_code == 200
    body = r.json()
    assert "date" in body
    assert "tasks" in body
    assert "events" in body


def test_context_meeting(client: TestClient):
    with patch("cluny.context.retrieve", return_value=[]):
        r = client.post("/context/meeting", json={"title": "Standup"})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Standup"
    assert "snippets" in data


def test_calendar_events(client: TestClient, tmp_path):
    ics = tmp_path / "cal.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Team sync\n"
        "DTSTART:20260901T100000Z\nEND:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    r = client.post("/calendar/import", json={"path": str(ics)})
    assert r.status_code == 200
    r2 = client.get("/calendar/events", params={"date": "2026-09-01"})
    assert r2.status_code == 200
    events = r2.json()["events"]
    assert any("Team sync" in e["summary"] for e in events)


def test_calendar_import_endpoint(client: TestClient, tmp_path):
    ics = tmp_path / "import.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Import test\n"
        "DTSTART:20260902T100000Z\nEND:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    r = client.post("/calendar/import", json={"path": str(ics)})
    assert r.status_code == 200
    assert r.json()["imported"] == 1

"""Deprecated CLI-only HTTP routes (not Kosistenz integration)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cluny.api import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("CLUNY_DATA_DIR", str(tmp_path / ".cluny"))
    monkeypatch.setenv("CLUNY_SUPERVISOR", "regex")
    return TestClient(create_app())


def _assert_deprecated(response) -> None:
    assert response.headers.get("Deprecation") == "true"
    assert response.headers.get("X-Cluny-Legacy") == "cli-only"


def test_legacy_task_crud(client: TestClient):
    r = client.post("/tasks", json={"title": "CLI task", "due_at": "tomorrow"})
    _assert_deprecated(r)
    assert r.status_code == 200
    tid = r.json()["id"]

    r2 = client.get("/tasks")
    _assert_deprecated(r2)
    assert len(r2.json()["tasks"]) == 1

    r3 = client.delete(f"/tasks/{tid}")
    _assert_deprecated(r3)
    assert r3.status_code == 200


def test_legacy_context_day(client: TestClient):
    client.post("/tasks", json={"title": "Day task", "due_at": "today"})
    r = client.post("/context/day", json={"date": "today"})
    _assert_deprecated(r)
    assert r.status_code == 200
    assert "tasks" in r.json()


def test_legacy_context_meeting(client: TestClient):
    with patch("cluny.context.retrieve", return_value=[]):
        r = client.post("/context/meeting", json={"title": "Standup"})
    _assert_deprecated(r)
    assert r.status_code == 200


def test_legacy_calendar(client: TestClient, tmp_path):
    ics = tmp_path / "cal.ics"
    ics.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Team sync\n"
        "DTSTART:20260901T100000Z\nEND:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    r = client.post("/calendar/import", json={"path": str(ics)})
    _assert_deprecated(r)
    assert r.status_code == 200

    r2 = client.get("/calendar/events", params={"date": "2026-09-01"})
    _assert_deprecated(r2)
    assert any("Team sync" in e["summary"] for e in r2.json()["events"])

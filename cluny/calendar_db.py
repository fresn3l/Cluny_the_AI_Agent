"""Read-only calendar events from imported ICS files."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cluny.config import Settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path(settings: Settings) -> Path:
    p = settings.data_dir / "calendar.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(settings)))
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            uid TEXT,
            summary TEXT NOT NULL,
            start_at TEXT,
            end_at TEXT,
            location TEXT,
            source_file TEXT,
            imported_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


@dataclass(frozen=True)
class EventRow:
    id: str
    uid: str | None
    summary: str
    start_at: str | None
    end_at: str | None
    location: str | None
    source_file: str | None


def _unfold_ics(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and out:
            out[-1] += line.strip()
        else:
            out.append(line)
    return "\n".join(out)


def _parse_ics_events(text: str) -> list[dict[str, str]]:
    unfolded = _unfold_ics(text)
    blocks = re.split(r"BEGIN:VEVENT", unfolded)[1:]
    events: list[dict[str, str]] = []
    for block in blocks:
        chunk = "BEGIN:VEVENT" + block.split("END:VEVENT")[0]
        fields: dict[str, str] = {}
        for line in chunk.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.split(";")[0].strip().upper()
            fields[key] = val.strip()
        if fields.get("SUMMARY"):
            events.append(fields)
    return events


def import_ics(path: Path, settings: Settings) -> int:
    """Parse an ICS file and upsert events. Returns count imported."""
    src = path.expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Not a file: {path}")
    text = src.read_text(encoding="utf-8", errors="replace")
    parsed = _parse_ics_events(text)
    conn = connect(settings)
    now = _utc_now()
    count = 0
    for ev in parsed:
        uid = ev.get("UID", uuid.uuid4().hex)
        eid = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO events (id, uid, summary, start_at, end_at, location, source_file, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                uid,
                ev.get("SUMMARY", "(no title)"),
                ev.get("DTSTART"),
                ev.get("DTEND"),
                ev.get("LOCATION"),
                str(src),
                now,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def list_upcoming(conn: sqlite3.Connection, *, limit: int = 20) -> list[EventRow]:
    cur = conn.execute(
        "SELECT * FROM events ORDER BY COALESCE(start_at, imported_at) ASC LIMIT ?",
        (limit,),
    )
    return [_row_from_sql(r) for r in cur.fetchall()]


def _row_from_sql(r: sqlite3.Row) -> EventRow:
    return EventRow(
        id=str(r["id"]),
        uid=str(r["uid"]) if r["uid"] else None,
        summary=str(r["summary"]),
        start_at=str(r["start_at"]) if r["start_at"] else None,
        end_at=str(r["end_at"]) if r["end_at"] else None,
        location=str(r["location"]) if r["location"] else None,
        source_file=str(r["source_file"]) if r["source_file"] else None,
    )


def _date_prefixes(date_str: str) -> tuple[str, ...]:
    """ISO and compact ICS prefixes (YYYY-MM-DD and YYYYMMDD)."""
    from cluny.dates import parse_due

    iso = parse_due(date_str) or date_str
    iso_prefix = iso[:10] if len(iso) >= 10 else date_str[:10]
    compact = iso_prefix.replace("-", "")
    if compact == iso_prefix:
        return (iso_prefix,)
    return (iso_prefix, compact)


def events_on_date(conn: sqlite3.Connection, date_str: str) -> list[EventRow]:
    """Match events whose start_at contains the date prefix (ICS DTSTART formats)."""
    prefixes = _date_prefixes(date_str)
    clauses = " OR ".join("start_at LIKE ?" for _ in prefixes)
    params = tuple(f"{p}%" for p in prefixes)
    cur = conn.execute(
        f"SELECT * FROM events WHERE {clauses} ORDER BY start_at ASC",
        params,
    )
    return [_row_from_sql(r) for r in cur.fetchall()]

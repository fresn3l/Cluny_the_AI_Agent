"""Accepted proposal pointers: proposal_id → kosistenz:{uuid}."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cluny.config import Settings


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db_path(settings: Settings) -> Path:
    p = settings.data_dir / "proposal_accepts.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path(settings)))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_accepts (
            proposal_id TEXT PRIMARY KEY,
            kosistenz_id TEXT NOT NULL,
            accepted_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def record_acceptance(
    settings: Settings,
    *,
    proposal_id: str,
    kosistenz_id: str,
) -> dict[str, str]:
    pid = str(proposal_id or "").strip()
    kid = str(kosistenz_id or "").strip()
    if not pid:
        raise ValueError("proposal_id is required")
    if not kid:
        raise ValueError("kosistenz_id is required")
    if not kid.startswith("kosistenz:"):
        kid = f"kosistenz:{kid}"
    conn = connect(settings)
    conn.execute(
        """
        INSERT INTO proposal_accepts (proposal_id, kosistenz_id, accepted_at)
        VALUES (?, ?, ?)
        ON CONFLICT(proposal_id) DO UPDATE SET
            kosistenz_id = excluded.kosistenz_id,
            accepted_at = excluded.accepted_at
        """,
        (pid, kid, _utc_now()),
    )
    conn.commit()
    conn.close()
    return {"proposal_id": pid, "kosistenz_id": kid}


def accepted_proposal_ids(settings: Settings) -> frozenset[str]:
    conn = connect(settings)
    cur = conn.execute("SELECT proposal_id FROM proposal_accepts")
    ids = frozenset(str(r[0]) for r in cur.fetchall())
    conn.close()
    return ids


def get_acceptance(settings: Settings, proposal_id: str) -> dict[str, str] | None:
    conn = connect(settings)
    cur = conn.execute(
        "SELECT proposal_id, kosistenz_id, accepted_at FROM proposal_accepts WHERE proposal_id = ?",
        (str(proposal_id).strip(),),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "proposal_id": str(row["proposal_id"]),
        "kosistenz_id": str(row["kosistenz_id"]),
        "accepted_at": str(row["accepted_at"]),
    }

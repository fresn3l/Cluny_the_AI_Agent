"""Proposal tools for the agent loop (Kosistenz inbox — not live CRUD)."""

from __future__ import annotations

from typing import Any

from cluny.config import Settings
from cluny.proposals import (
    ProposalCitation,
    WorkProposal,
    normalize_due,
    stable_proposal_id,
)
from cluny.tools.registry import Tool

# In-process proposals from the current agent turn (also returned in tool JSON).
_LAST_PROPOSALS: list[dict[str, Any]] = []


def last_agent_proposals() -> list[dict[str, Any]]:
    return list(_LAST_PROPOSALS)


def clear_agent_proposals() -> None:
    _LAST_PROPOSALS.clear()


def _create_proposal(args: dict[str, Any], settings: Settings) -> dict[str, Any]:  # noqa: ARG001
    title = str(args.get("title", "")).strip()
    if not title:
        return {"error": "title is required"}
    est = args.get("estimate_minutes")
    estimate = int(est) if isinstance(est, (int, float)) else None
    due = normalize_due(args.get("due"))
    kw = args.get("keywords") or []
    keywords = [str(k).strip() for k in kw if str(k).strip()] if isinstance(kw, list) else []
    citations_raw = args.get("citations") or []
    citations: list[ProposalCitation] = []
    if isinstance(citations_raw, list):
        for c in citations_raw:
            if isinstance(c, dict):
                ct = str(c.get("title") or "").strip()
                if ct:
                    citations.append(
                        ProposalCitation(
                            title=ct,
                            locator=str(c.get("locator") or "").strip() or None,
                        )
                    )
            elif isinstance(c, str) and c.strip():
                citations.append(ProposalCitation(title=c.strip()))
    pid = stable_proposal_id(
        title=title,
        due=due,
        keywords=keywords,
        explicit_id=str(args.get("id") or "").strip() or None,
    )
    proposal = WorkProposal(
        id=pid,
        title=title,
        estimate_minutes=estimate,
        due=due,
        keywords=keywords,
        citations=citations,
    )
    payload = proposal.to_dict()
    _LAST_PROPOSALS.append(payload)
    return {
        **payload,
        "note": (
            "Proposal recorded for Kosistenz inbox. "
            "This is NOT a live Cluny or Kosistenz to-do. "
            "Do not invent clock times."
        ),
    }


def _list_tasks_scratch(args: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Scratch list only — never the Kosistenz Today / All Work / phone list."""
    from cluny.tasks_db import connect, list_tasks

    conn = connect(settings)
    status = str(args.get("status", "")).strip() or None
    project = str(args.get("project_id", "")).strip() or None
    due_week = bool(args.get("due_week", False))
    rows = list_tasks(conn, status=status, project_id=project, due_week=due_week)
    conn.close()
    return {
        "scratch_only": True,
        "warning": (
            "These are Cluny scratch tasks (tasks.sqlite). "
            "They are NOT Kosistenz Today, All Work, or the iPhone list. "
            "Prefer the Kosistenz life snapshot in the user message for what's due."
        ),
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "due_at": t.due_at,
                "notes": t.notes,
                "project_id": t.project_id,
                "recurrence": t.recurrence,
            }
            for t in rows
        ],
    }


def build_proposal_tools(settings: Settings) -> list[Tool]:
    return [
        Tool(
            name="create_proposal",
            description=(
                "Propose a work item for the Kosistenz inbox. "
                "Use after search_brain when suggesting work. "
                "due must be YYYY-MM-DD only — never a clock time. "
                "Does not create a live to-do."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "estimate_minutes": {"type": "integer"},
                    "due": {
                        "type": "string",
                        "description": "Calendar day YYYY-MM-DD only, or omit",
                    },
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "locator": {"type": "string"},
                            },
                        },
                    },
                    "id": {
                        "type": "string",
                        "description": "Optional stable id (hash of source row)",
                    },
                },
                "required": ["title"],
            },
            handler=lambda args: _create_proposal(args, settings),
        ),
    ]


def build_scratch_list_tool(settings: Settings) -> list[Tool]:
    return [
        Tool(
            name="list_scratch_tasks",
            description=(
                "List Cluny scratch tasks only. NOT Kosistenz Today/All Work. "
                "Prefer life snapshot in context for what's due this week."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "done"]},
                    "project_id": {"type": "string"},
                    "due_week": {"type": "boolean"},
                },
            },
            handler=lambda args: _list_tasks_scratch(args, settings),
        ),
    ]

"""Ollama tool-calling agent loop for Cluny."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from cluny.brain_config import AGENT_MODE_PROMPT_KEYS, DEFAULT_PROMPTS, get_prompt
from cluny.config import Settings
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.tools.calendar import build_calendar_tools
from cluny.tools.knowledge import build_knowledge_tools
from cluny.tools.proposals import (
    build_proposal_tools,
    build_scratch_list_tool,
    clear_agent_proposals,
    last_agent_proposals,
)
from cluny.tools.registry import Tool, ToolRegistry
from cluny.tools.tasks import build_task_tools

AgentMode = Literal["knowledge", "tasks", "all", "planner"]

KNOWLEDGE_AGENT_SYSTEM = DEFAULT_PROMPTS["knowledge_agent_system"]
TASKS_AGENT_SYSTEM = DEFAULT_PROMPTS["tasks_agent_system"]
ALL_AGENT_SYSTEM = DEFAULT_PROMPTS["all_agent_system"]
PLANNER_AGENT_SYSTEM = DEFAULT_PROMPTS["planner_agent_system"]

MAX_TURNS = 8
PLANNER_MAX_TURNS = 12

# Live CRUD against Cluny tasks.sqlite — standalone scratch mode only.
_LIVE_TASK_CRUD = frozenset({"create_task", "update_task", "complete_task", "list_tasks"})
_KNOWLEDGE_TOOL_NAMES = frozenset({"search_brain", "add_note"})
_PROPOSAL_TOOL_NAMES = frozenset({"create_proposal"})
_SNAPSHOT_CAL_NAMES = frozenset({"week_from_snapshot", "events_on_date"})
_SCRATCH_LIST = frozenset({"list_scratch_tasks"})


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[str] = field(default_factory=list)
    proposals: list[dict] = field(default_factory=list)


def _build_registry(settings: Settings, mode: AgentMode) -> ToolRegistry:
    tools: list[Tool] = []
    if mode in ("knowledge", "all", "planner"):
        tools.extend(build_knowledge_tools(settings))
    if mode in ("all", "planner"):
        # Propose work for Kosistenz; do not live-CRUD Cluny tasks.sqlite.
        tools.extend(build_proposal_tools(settings))
        tools.extend(build_calendar_tools(settings))
        tools.extend(build_scratch_list_tool(settings))
    if mode == "tasks":
        # Standalone scratch only — not Kosistenz All Work / Today / iPhone.
        tools.extend(build_task_tools(settings))
    return ToolRegistry(tools)


def _system_for_mode(mode: AgentMode, settings: Settings | None = None) -> str:
    key = AGENT_MODE_PROMPT_KEYS[mode]
    return get_prompt(key, settings=settings)


def _max_turns(mode: AgentMode) -> int:
    return PLANNER_MAX_TURNS if mode == "planner" else MAX_TURNS


def _tool_allowed(mode: AgentMode, name: str) -> bool:
    if mode == "knowledge":
        return name in _KNOWLEDGE_TOOL_NAMES
    if mode == "tasks":
        return name in _LIVE_TASK_CRUD
    if mode in ("planner", "all"):
        if name in _LIVE_TASK_CRUD:
            return False
        return name in (
            _KNOWLEDGE_TOOL_NAMES | _PROPOSAL_TOOL_NAMES | _SNAPSHOT_CAL_NAMES | _SCRATCH_LIST
        )
    return False


def run_agent(
    question: str,
    *,
    settings: Settings | None = None,
    max_turns: int | None = None,
    mode: AgentMode = "knowledge",
) -> AgentResult:
    settings = settings or Settings.load()
    ollama = OllamaClient(settings)
    registry = _build_registry(settings, mode)
    turns = max_turns if max_turns is not None else _max_turns(mode)
    clear_agent_proposals()

    messages: list[dict] = [
        {"role": "system", "content": _system_for_mode(mode, settings)},
        {"role": "user", "content": question},
    ]
    tool_trace: list[str] = []

    for _ in range(turns):
        try:
            data = ollama.chat_with_tools(messages, registry.schemas())
        except OllamaError:
            raise

        msg = data.get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            return AgentResult(
                answer=str(content).strip(),
                tool_calls=tool_trace,
                proposals=last_agent_proposals(),
            )

        messages.append(msg)

        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
            else:
                args = raw_args if isinstance(raw_args, dict) else {}

            if not _tool_allowed(mode, name):
                result = json.dumps(
                    {
                        "error": (
                            f"Tool {name} not available in {mode} mode. "
                            "For Kosistenz brain use search_brain then create_proposal. "
                            "Do not create live tasks or pick clock times."
                        )
                    }
                )
            else:
                result = registry.execute(name, args)

            tool_trace.append(f"{name}({json.dumps(args)})")
            messages.append({"role": "tool", "content": result})

    return AgentResult(
        answer="I reached the maximum number of tool steps. Please try a simpler question.",
        tool_calls=tool_trace,
        proposals=last_agent_proposals(),
    )

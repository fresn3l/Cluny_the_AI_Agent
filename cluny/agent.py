"""Ollama tool-calling agent loop for Cluny."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from cluny.config import Settings
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.query import SYSTEM_PROMPT
from cluny.tools.knowledge import build_knowledge_tools
from cluny.tools.registry import Tool, ToolRegistry
from cluny.tools.tasks import build_task_tools

AgentMode = Literal["knowledge", "tasks", "all"]

KNOWLEDGE_AGENT_SYSTEM = (
    SYSTEM_PROMPT
    + " You have tools to search the user's indexed notes (search_brain) and save "
    "short notes (add_note). Use search_brain when you need facts from their library. "
    "Use add_note only when the user explicitly wants something remembered. "
    "Call one tool at a time, then synthesize a final answer."
)

TASKS_AGENT_SYSTEM = (
    "You are Cluny's task assistant. You help manage the user's to-do list using "
    "task tools only. Use list_tasks to see what's open. Use create_task when the user "
    "wants something added. Use complete_task or update_task only when they explicitly "
    "ask to change a task. Do not invent tasks. Call one tool at a time."
)

ALL_AGENT_SYSTEM = (
    SYSTEM_PROMPT
    + " You have knowledge tools (search_brain, add_note) and task tools "
    "(create_task, list_tasks, update_task, complete_task). Use knowledge tools for "
    "indexed notes; use task tools for to-dos. Never mix them unnecessarily. "
    "Call one tool at a time."
)

MAX_TURNS = 8


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[str] = field(default_factory=list)


def _build_registry(settings: Settings, mode: AgentMode) -> ToolRegistry:
    tools: list[Tool] = []
    if mode in ("knowledge", "all"):
        tools.extend(build_knowledge_tools(settings))
    if mode in ("tasks", "all"):
        tools.extend(build_task_tools(settings))
    return ToolRegistry(tools)


def _system_for_mode(mode: AgentMode) -> str:
    if mode == "tasks":
        return TASKS_AGENT_SYSTEM
    if mode == "all":
        return ALL_AGENT_SYSTEM
    return KNOWLEDGE_AGENT_SYSTEM


def run_agent(
    question: str,
    *,
    settings: Settings | None = None,
    max_turns: int = MAX_TURNS,
    mode: AgentMode = "knowledge",
) -> AgentResult:
    settings = settings or Settings.from_env()
    ollama = OllamaClient(settings)
    registry = _build_registry(settings, mode)

    messages: list[dict] = [
        {"role": "system", "content": _system_for_mode(mode)},
        {"role": "user", "content": question},
    ]
    tool_trace: list[str] = []

    for _ in range(max_turns):
        try:
            data = ollama.chat_with_tools(messages, registry.schemas())
        except OllamaError:
            raise

        msg = data.get("message") or {}
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            return AgentResult(answer=str(content).strip(), tool_calls=tool_trace)

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

            if mode == "knowledge" and name in (
                "create_task",
                "list_tasks",
                "update_task",
                "complete_task",
            ):
                result = json.dumps({"error": f"Tool {name} not available in knowledge mode"})
            elif mode == "tasks" and name in ("search_brain", "add_note"):
                result = json.dumps({"error": f"Tool {name} not available in tasks mode"})
            else:
                result = registry.execute(name, args)

            tool_trace.append(f"{name}({json.dumps(args)})")
            messages.append({"role": "tool", "content": result})

    return AgentResult(
        answer="I reached the maximum number of tool steps. Please try a simpler question.",
        tool_calls=tool_trace,
    )

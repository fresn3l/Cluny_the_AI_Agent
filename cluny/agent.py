"""Ollama tool-calling agent loop for Cluny."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from cluny.config import Settings
from cluny.ollama_client import OllamaClient, OllamaError
from cluny.query import SYSTEM_PROMPT
from cluny.tools.knowledge import build_knowledge_tools
from cluny.tools.registry import ToolRegistry

AGENT_SYSTEM = (
    SYSTEM_PROMPT
    + " You have tools to search the user's indexed notes (search_brain) and save "
    "short notes (add_note). Use search_brain when you need facts from their library. "
    "Use add_note only when the user explicitly wants something remembered. "
    "Call one tool at a time, then synthesize a final answer."
)

MAX_TURNS = 8
TOOL_TIMEOUT_SEC = 30


@dataclass
class AgentResult:
    answer: str
    tool_calls: list[str] = field(default_factory=list)


def run_agent(
    question: str,
    *,
    settings: Settings | None = None,
    max_turns: int = MAX_TURNS,
) -> AgentResult:
    settings = settings or Settings.from_env()
    ollama = OllamaClient(settings)
    registry = ToolRegistry(build_knowledge_tools(settings))

    messages: list[dict] = [
        {"role": "system", "content": AGENT_SYSTEM},
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

            tool_trace.append(f"{name}({json.dumps(args)})")
            result = registry.execute(name, args)
            messages.append({"role": "tool", "content": result})

    return AgentResult(
        answer="I reached the maximum number of tool steps. Please try a simpler question.",
        tool_calls=tool_trace,
    )

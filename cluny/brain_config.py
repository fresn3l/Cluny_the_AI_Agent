"""Editable brain instructions stored in CLUNY_DATA_DIR/brain_config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cluny.config import Settings

CONFIG_VERSION = 1
CONFIG_FILENAME = "brain_config.json"

_DEFAULT_RAG_SYSTEM = (
    "You are Cluny, a local second-brain assistant. Answer using only the provided "
    "context snippets from the user's indexed notes. If the answer is not in the context, "
    "say you do not have that information in the indexed notes. Be concise. Cite which "
    "snippet supports each claim when possible. Do not invent facts or claim you searched "
    "the internet. If you are uncertain, say so rather than guessing."
)

_DEFAULT_RAG_USER_TEMPLATE = "Context from indexed notes:\n\n{context}\n\nQuestion: {question}"

_DEFAULT_RERANK_SYSTEM = (
    "Score how relevant each numbered snippet is to the question on a scale of 0-10. "
    "Reply with ONLY comma-separated scores in snippet order (e.g. 8,3,9). No other text."
)

_DEFAULT_PROPOSE_SYSTEM = (
    "You suggest work items for the user. Kosistenz owns the calendar and week clock — "
    "you only propose work, never pick clock times or days.\n"
    "Use the live Kosistenz context and any retrieved journal/analytics snippets from "
    "indexed history. Ground proposals in patterns you see (missed goals, slipped tasks, "
    "journal themes) when relevant.\n"
    "Reply with ONLY valid JSON, no markdown:\n"
    '{"proposals": [{"title": "string", "estimate_minutes": number or null, '
    '"due": "YYYY-MM-DD or null", "keywords": ["string"]}]}\n'
    "Use an empty proposals array if nothing to suggest."
)

_DEFAULT_ROUTER_SYSTEM = (
    "Classify the user message into exactly one route. Reply with ONLY one word:\n"
    "ask — general question answerable from retrieved notes in one shot\n"
    "knowledge_agent — needs searching indexed notes with tools\n"
    "tasks_agent — about to-do list, deadlines, completing tasks\n"
    "calendar — meetings, schedule, appointments\n"
    "planner — needs BOTH notes search AND task action (compound request)\n"
)

_DEFAULT_KNOWLEDGE_AGENT_SYSTEM = (
    _DEFAULT_RAG_SYSTEM
    + " You have tools to search the user's indexed notes (search_brain) and save "
    "short notes (add_note). Use search_brain when you need facts from their library. "
    "Use add_note only when the user explicitly wants something remembered. "
    "Call one tool at a time, then synthesize a final answer."
)

_DEFAULT_TASKS_AGENT_SYSTEM = (
    "You are Cluny's task assistant. You help manage the user's to-do list using "
    "task tools only. Use list_tasks to see what's open. Use create_task when the user "
    "wants something added. Use complete_task or update_task only when they explicitly "
    "ask to change a task. Do not invent tasks. Call one tool at a time."
)

_DEFAULT_ALL_AGENT_SYSTEM = (
    _DEFAULT_RAG_SYSTEM
    + " You have knowledge tools (search_brain, add_note), task tools "
    "(create_task, list_tasks, update_task, complete_task), and calendar tools "
    "(list_events, events_on_date). Use the right tool for the request. "
    "Call one tool at a time."
)

_DEFAULT_PLANNER_AGENT_SYSTEM = (
    _DEFAULT_RAG_SYSTEM
    + " You are a planner. The user wants a compound outcome. First use search_brain "
    "to gather facts from indexed notes when needed, then use task tools to create or "
    "update tasks. You may also use calendar tools for scheduling context. "
    "Call one tool at a time, up to several steps, then give a final summary."
)

DEFAULT_PROMPTS: dict[str, str] = {
    "rag_system": _DEFAULT_RAG_SYSTEM,
    "rag_user_template": _DEFAULT_RAG_USER_TEMPLATE,
    "rerank_system": _DEFAULT_RERANK_SYSTEM,
    "propose_system": _DEFAULT_PROPOSE_SYSTEM,
    "router_system": _DEFAULT_ROUTER_SYSTEM,
    "knowledge_agent_system": _DEFAULT_KNOWLEDGE_AGENT_SYSTEM,
    "tasks_agent_system": _DEFAULT_TASKS_AGENT_SYSTEM,
    "all_agent_system": _DEFAULT_ALL_AGENT_SYSTEM,
    "planner_agent_system": _DEFAULT_PLANNER_AGENT_SYSTEM,
}

PROMPT_KEYS = tuple(DEFAULT_PROMPTS.keys())

AGENT_MODE_PROMPT_KEYS: dict[str, str] = {
    "knowledge": "knowledge_agent_system",
    "tasks": "tasks_agent_system",
    "all": "all_agent_system",
    "planner": "planner_agent_system",
}

_DEFAULT_EMPTY_INDEX_MESSAGE = (
    "No documents in the index yet. Use `cluny add`, `cluny add-dir`, or `cluny ingest-text` first."
)

_DEFAULT_EMPTY_COLLECTION_MESSAGE = (
    "No documents in that collection yet. Add files with `cluny collection add`, "
    "or choose a different collection."
)

_CACHE: dict[str, BrainConfig] = {}


@dataclass
class BrainPromptOverrides:
    rag_system: str | None = None
    rag_user_template: str | None = None
    rerank_system: str | None = None
    propose_system: str | None = None
    router_system: str | None = None
    knowledge_agent_system: str | None = None
    tasks_agent_system: str | None = None
    all_agent_system: str | None = None
    planner_agent_system: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BrainPromptOverrides:
        if not data:
            return cls()
        kwargs: dict[str, str | None] = {}
        for key in PROMPT_KEYS:
            val = data.get(key)
            kwargs[key] = str(val) if val is not None else None
        return cls(**kwargs)

    def to_dict(self) -> dict[str, str | None]:
        return {key: getattr(self, key) for key in PROMPT_KEYS}

    def get_override(self, key: str) -> str | None:
        return getattr(self, key, None)


@dataclass
class BrainBehavior:
    supervisor_mode: str | None = None
    max_proposals: int | None = None
    empty_index_message: str | None = None
    empty_collection_message: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BrainBehavior:
        if not data:
            return cls()
        max_p = data.get("max_proposals")
        return cls(
            supervisor_mode=str(data["supervisor_mode"]) if data.get("supervisor_mode") else None,
            max_proposals=int(max_p) if max_p is not None else None,
            empty_index_message=(
                str(data["empty_index_message"]) if data.get("empty_index_message") else None
            ),
            empty_collection_message=(
                str(data["empty_collection_message"])
                if data.get("empty_collection_message")
                else None
            ),
        )

    def to_dict(self) -> dict[str, str | int | None]:
        return asdict(self)


@dataclass
class BrainConfig:
    version: int = CONFIG_VERSION
    global_persona: str = ""
    prompts: BrainPromptOverrides = field(default_factory=BrainPromptOverrides)
    behavior: BrainBehavior = field(default_factory=BrainBehavior)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrainConfig:
        return cls(
            version=int(data.get("version", CONFIG_VERSION)),
            global_persona=str(data.get("global_persona", "")),
            prompts=BrainPromptOverrides.from_dict(data.get("prompts")),
            behavior=BrainBehavior.from_dict(data.get("behavior")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "global_persona": self.global_persona,
            "prompts": self.prompts.to_dict(),
            "behavior": self.behavior.to_dict(),
        }


DEFAULT_EMPTY_INDEX_MESSAGE = _DEFAULT_EMPTY_INDEX_MESSAGE
DEFAULT_EMPTY_COLLECTION_MESSAGE = _DEFAULT_EMPTY_COLLECTION_MESSAGE


def config_path(settings: Settings) -> Path:
    return settings.data_dir / CONFIG_FILENAME


def default_brain_config() -> BrainConfig:
    return BrainConfig()


def invalidate_brain_config_cache() -> None:
    _CACHE.clear()


def load_brain_config(settings: Settings) -> BrainConfig:
    cache_key = str(settings.data_dir.resolve())
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    path = config_path(settings)
    if not path.is_file():
        cfg = default_brain_config()
        _CACHE[cache_key] = cfg
        return cfg

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg = BrainConfig.from_dict(data)
        else:
            cfg = default_brain_config()
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        cfg = default_brain_config()

    _CACHE[cache_key] = cfg
    return cfg


def save_brain_config(settings: Settings, config: BrainConfig) -> None:
    path = config_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    invalidate_brain_config_cache()
    _CACHE[str(settings.data_dir.resolve())] = config


def _apply_persona(text: str, persona: str) -> str:
    persona = persona.strip()
    if not persona:
        return text
    return f"{persona}\n\n{text}"


def get_prompt(
    key: str,
    *,
    settings: Settings | None = None,
    config: BrainConfig | None = None,
    preview_overrides: dict[str, str] | None = None,
) -> str:
    """Return effective prompt text (override → default) with optional global persona."""
    if key not in DEFAULT_PROMPTS:
        raise KeyError(f"Unknown prompt key: {key}")

    cfg = config or load_brain_config(settings or Settings.load())

    if preview_overrides and key in preview_overrides:
        base = preview_overrides[key]
    else:
        override = cfg.prompts.get_override(key)
        base = override if override is not None else DEFAULT_PROMPTS[key]

    return _apply_persona(base, cfg.global_persona)


def get_rag_user_template(
    *,
    settings: Settings | None = None,
    config: BrainConfig | None = None,
) -> str:
    """RAG user template is not prefixed with global persona (it's a format string)."""
    cfg = config or load_brain_config(settings or Settings.load())
    override = cfg.prompts.rag_user_template
    return override if override is not None else DEFAULT_PROMPTS["rag_user_template"]


def get_empty_index_message(
    *,
    settings: Settings | None = None,
    config: BrainConfig | None = None,
) -> str:
    cfg = config or load_brain_config(settings or Settings.load())
    override = cfg.behavior.empty_index_message
    return override if override is not None else _DEFAULT_EMPTY_INDEX_MESSAGE


def get_empty_collection_message(
    *,
    settings: Settings | None = None,
    config: BrainConfig | None = None,
) -> str:
    cfg = config or load_brain_config(settings or Settings.load())
    override = cfg.behavior.empty_collection_message
    return override if override is not None else _DEFAULT_EMPTY_COLLECTION_MESSAGE


def get_supervisor_mode(
    *,
    settings: Settings | None = None,
    config: BrainConfig | None = None,
) -> str:
    settings = settings or Settings.load()
    cfg = config or load_brain_config(settings)
    if cfg.behavior.supervisor_mode in ("llm", "regex"):
        return cfg.behavior.supervisor_mode
    return settings.supervisor_mode


def get_max_proposals(
    *,
    settings: Settings | None = None,
    config: BrainConfig | None = None,
    default: int = 5,
) -> int:
    cfg = config or load_brain_config(settings or Settings.load())
    if cfg.behavior.max_proposals is not None and cfg.behavior.max_proposals > 0:
        return cfg.behavior.max_proposals
    return default


def effective_config(settings: Settings | None = None) -> dict[str, Any]:
    """Merged defaults + overrides for API/GUI display."""
    settings = settings or Settings.load()
    cfg = load_brain_config(settings)
    effective_prompts = {key: get_prompt(key, settings=settings, config=cfg) for key in PROMPT_KEYS}
    return {
        "version": cfg.version,
        "global_persona": cfg.global_persona,
        "prompts": effective_prompts,
        "overrides": cfg.prompts.to_dict(),
        "behavior": {
            "supervisor_mode": get_supervisor_mode(settings=settings, config=cfg),
            "max_proposals": get_max_proposals(settings=settings, config=cfg),
            "empty_index_message": get_empty_index_message(settings=settings, config=cfg),
            "empty_collection_message": get_empty_collection_message(settings=settings, config=cfg),
        },
        "behavior_overrides": cfg.behavior.to_dict(),
        "defaults": dict(DEFAULT_PROMPTS),
    }


PROMPT_LABELS: dict[str, str] = {
    "rag_system": "RAG / Ask system",
    "rag_user_template": "RAG user template",
    "rerank_system": "Rerank scorer",
    "propose_system": "Work proposals",
    "router_system": "Intent router",
    "knowledge_agent_system": "Knowledge agent",
    "tasks_agent_system": "Tasks agent",
    "all_agent_system": "All-tools agent",
    "planner_agent_system": "Planner agent",
}


def editor_text_for_prompt(key: str, cfg: BrainConfig) -> str:
    """Text shown in the editor (override or shipped default, without persona)."""
    override = cfg.prompts.get_override(key)
    return override if override is not None else DEFAULT_PROMPTS[key]


def override_from_editor(text: str, key: str) -> str | None:
    """Persist editor content: blank or unchanged default → None (use shipped default)."""
    stripped = text.strip()
    if not stripped:
        return None
    if stripped == DEFAULT_PROMPTS[key]:
        return None
    return stripped


def apply_config_update(
    settings: Settings,
    *,
    global_persona: str | None = None,
    prompts: dict[str, str | None] | None = None,
    behavior: dict[str, Any] | None = None,
) -> BrainConfig:
    """Merge partial updates into brain_config.json."""
    cfg = load_brain_config(settings)
    if global_persona is not None:
        cfg.global_persona = global_persona
    if prompts is not None:
        current = cfg.prompts.to_dict()
        for key, val in prompts.items():
            if key not in PROMPT_KEYS:
                raise ValueError(f"Unknown prompt key: {key}")
            current[key] = val if val else None
        cfg.prompts = BrainPromptOverrides.from_dict(current)
    if behavior is not None:
        merged = cfg.behavior.to_dict()
        for key, val in behavior.items():
            if key not in merged:
                raise ValueError(f"Unknown behavior key: {key}")
            merged[key] = val
        cfg.behavior = BrainBehavior.from_dict(merged)
    save_brain_config(settings, cfg)
    return cfg


def reset_brain_config(
    settings: Settings,
    *,
    prompt_key: str | None = None,
    reset_behavior: bool = False,
    reset_persona: bool = False,
    reset_all: bool = False,
) -> BrainConfig:
    """Clear overrides (all, one prompt, behavior, or persona)."""
    if reset_all:
        cfg = default_brain_config()
        save_brain_config(settings, cfg)
        return cfg

    cfg = load_brain_config(settings)
    if reset_persona:
        cfg.global_persona = ""
    if reset_behavior:
        cfg.behavior = BrainBehavior()
    if prompt_key:
        if prompt_key not in PROMPT_KEYS:
            raise ValueError(f"Unknown prompt key: {prompt_key}")
        setattr(cfg.prompts, prompt_key, None)
    save_brain_config(settings, cfg)
    return cfg


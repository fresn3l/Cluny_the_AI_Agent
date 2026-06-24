"""Per-user GUI/CLI preferences stored outside the repo .env."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from cluny.config import Settings


@dataclass
class UserConfig:
    chat_model: str = "llama3.2"
    embed_model: str = "nomic-embed-text"
    retrieval_k: int = 5
    hybrid_vector_weight: float = 0.5
    agent_mode: str = "ask"

    @classmethod
    def from_dict(cls, data: dict) -> UserConfig:
        return cls(
            chat_model=str(data.get("chat_model", "llama3.2")),
            embed_model=str(data.get("embed_model", "nomic-embed-text")),
            retrieval_k=int(data.get("retrieval_k", 5)),
            hybrid_vector_weight=float(data.get("hybrid_vector_weight", 0.5)),
            agent_mode=str(data.get("agent_mode", "ask")),
        )


def config_path(settings: Settings) -> Path:
    return settings.data_dir / "user_config.json"


def load_user_config(settings: Settings) -> UserConfig:
    path = config_path(settings)
    if not path.is_file():
        return UserConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return UserConfig.from_dict(data)
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return UserConfig()


def save_user_config(settings: Settings, config: UserConfig) -> None:
    path = config_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

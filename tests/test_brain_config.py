"""Tests for editable brain configuration (Sprint 16 Phase A)."""

from __future__ import annotations

import json

import pytest

from cluny.brain_config import (
    BrainConfig,
    BrainPromptOverrides,
    DEFAULT_PROMPTS,
    config_path,
    effective_config,
    get_empty_index_message,
    get_prompt,
    invalidate_brain_config_cache,
    load_brain_config,
    save_brain_config,
)


@pytest.fixture(autouse=True)
def _clear_brain_cache():
    invalidate_brain_config_cache()
    yield
    invalidate_brain_config_cache()


def test_defaults_when_no_file(settings):
    cfg = load_brain_config(settings)
    assert cfg.global_persona == ""
    assert cfg.prompts.rag_system is None
    assert get_prompt("rag_system", settings=settings) == DEFAULT_PROMPTS["rag_system"]


def test_prompt_override(settings):
    cfg = BrainConfig(
        prompts=BrainPromptOverrides(rag_system="Custom RAG instructions."),
    )
    save_brain_config(settings, cfg)
    assert config_path(settings).is_file()
    assert get_prompt("rag_system", settings=settings) == "Custom RAG instructions."


def test_global_persona_prepended(settings):
    cfg = BrainConfig(global_persona="You are Elijah's brain.")
    save_brain_config(settings, cfg)
    text = get_prompt("rag_system", settings=settings)
    assert text.startswith("You are Elijah's brain.")
    assert DEFAULT_PROMPTS["rag_system"] in text


def test_save_roundtrip(settings):
    cfg = BrainConfig(
        global_persona="Persona",
        prompts=BrainPromptOverrides(propose_system="Propose differently."),
    )
    save_brain_config(settings, cfg)
    data = json.loads(config_path(settings).read_text(encoding="utf-8"))
    assert data["global_persona"] == "Persona"
    assert data["prompts"]["propose_system"] == "Propose differently."
    loaded = load_brain_config(settings)
    assert loaded.global_persona == "Persona"
    assert loaded.prompts.propose_system == "Propose differently."


def test_empty_index_message_override(settings):
    cfg = BrainConfig()
    cfg.behavior.empty_index_message = "Nothing indexed yet — add notes first."
    save_brain_config(settings, cfg)
    assert get_empty_index_message(settings=settings) == "Nothing indexed yet — add notes first."


def test_effective_config_includes_defaults_and_overrides(settings):
    cfg = BrainConfig(prompts=BrainPromptOverrides(router_system="Route carefully."))
    save_brain_config(settings, cfg)
    eff = effective_config(settings)
    assert "Route carefully." in eff["prompts"]["router_system"]
    assert eff["overrides"]["router_system"] == "Route carefully."
    assert eff["defaults"]["rag_system"] == DEFAULT_PROMPTS["rag_system"]


def test_preview_overrides_without_save(settings):
    cfg = load_brain_config(settings)
    text = get_prompt(
        "propose_system",
        settings=settings,
        config=cfg,
        preview_overrides={"propose_system": "Preview only."},
    )
    assert text == "Preview only."
    assert get_prompt("propose_system", settings=settings) == DEFAULT_PROMPTS["propose_system"]


def test_apply_config_update_and_reset(settings):
    from cluny.brain_config import apply_config_update, reset_brain_config

    apply_config_update(
        settings,
        global_persona="Persona",
        prompts={"router_system": "Route X."},
        behavior={"max_proposals": 3},
    )
    cfg = load_brain_config(settings)
    assert cfg.global_persona == "Persona"
    assert cfg.prompts.router_system == "Route X."
    assert cfg.behavior.max_proposals == 3
    reset_brain_config(settings, prompt_key="router_system")
    cfg = load_brain_config(settings)
    assert cfg.prompts.router_system is None


def test_override_from_editor(settings):
    from cluny.brain_config import override_from_editor

    assert override_from_editor("", "rag_system") is None
    assert override_from_editor(DEFAULT_PROMPTS["rag_system"], "rag_system") is None
    assert override_from_editor("Unique prompt", "rag_system") == "Unique prompt"

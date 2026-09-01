"""Tests for brain config export/import (Sprint 16 Phase E)."""

from __future__ import annotations

import json

import pytest

from cluny.brain_config import (
    export_brain_config_dict,
    export_brain_config_to_path,
    import_brain_config,
    import_brain_config_from_path,
    invalidate_brain_config_cache,
    load_brain_config,
    validate_brain_config_dict,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_brain_config_cache()
    yield
    invalidate_brain_config_cache()


def test_export_import_roundtrip(settings, tmp_path):
    import_brain_config(
        settings,
        {
            "version": 1,
            "global_persona": "Test persona",
            "prompts": {"rag_system": "Custom RAG"},
            "behavior": {"max_proposals": 3},
        },
    )
    exported = export_brain_config_dict(settings)
    assert exported["global_persona"] == "Test persona"
    assert exported["prompts"]["rag_system"] == "Custom RAG"

    out = tmp_path / "exported.json"
    export_brain_config_to_path(settings, out)
    assert out.is_file()

    invalidate_brain_config_cache()
    reset_path = settings.data_dir / "brain_config.json"
    if reset_path.is_file():
        reset_path.unlink()

    import_brain_config_from_path(settings, out)
    cfg = load_brain_config(settings)
    assert cfg.global_persona == "Test persona"
    assert cfg.prompts.rag_system == "Custom RAG"
    assert cfg.behavior.max_proposals == 3


def test_validate_rejects_unknown_prompt_key():
    with pytest.raises(ValueError, match="Unknown prompt key"):
        validate_brain_config_dict({"prompts": {"not_real": "x"}})


def test_validate_rejects_bad_supervisor_mode():
    with pytest.raises(ValueError, match="supervisor_mode"):
        validate_brain_config_dict({"behavior": {"supervisor_mode": "magic"}})


def test_import_invalid_json_file(settings, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        import_brain_config_from_path(settings, bad)

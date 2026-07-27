"""Model context-window discovery and budget derivation tests."""

import json

import pytest

from app.llm.context_window import (
    derive_context_budget,
    detect_context_window,
    resolve_model_context_window,
)


def test_detect_context_window_prefers_nested_text_config():
    detected = detect_context_window(
        {
            "max_position_embeddings": 4096,
            "text_config": {"max_position_embeddings": 8192},
        }
    )

    assert detected == (8192, "text_config.max_position_embeddings")


def test_resolve_context_window_reads_local_model_config(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"max_position_embeddings": 8192}),
        encoding="utf-8",
    )

    info = resolve_model_context_window(str(tmp_path), fallback_tokens=4096)

    assert info.tokens == 8192
    assert info.declared_tokens == 8192
    assert info.source == "config.json:max_position_embeddings"


def test_override_can_cap_but_cannot_expand_declared_limit(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"max_position_embeddings": 8192}),
        encoding="utf-8",
    )

    capped = resolve_model_context_window(str(tmp_path), override_tokens=4096)
    expanded = resolve_model_context_window(str(tmp_path), override_tokens=16384)

    assert capped.tokens == 4096
    assert capped.declared_tokens == 8192
    assert "cap over" in capped.source
    assert expanded.tokens == 8192


def test_tokenizer_sentinel_is_ignored_and_fallback_is_used(tmp_path):
    (tmp_path / "tokenizer_config.json").write_text(
        json.dumps({"model_max_length": 1000000000000000019884624838656}),
        encoding="utf-8",
    )

    info = resolve_model_context_window(str(tmp_path), fallback_tokens=4096)

    assert info.tokens == 4096
    assert info.declared_tokens is None
    assert "metadata unavailable" in info.source


def test_derive_context_budget_reserves_generation_and_safety_space():
    budget = derive_context_budget(
        8192,
        output_reserve_tokens=1024,
        safety_tokens=256,
        compact_trigger_ratio=0.8,
    )

    assert budget.max_prompt_tokens == 6912
    assert budget.compact_trigger_tokens == 5529


def test_derive_context_budget_rejects_an_unusable_remainder():
    with pytest.raises(ValueError, match="fewer than 1200"):
        derive_context_budget(
            2048,
            output_reserve_tokens=1024,
            safety_tokens=256,
            compact_trigger_ratio=0.8,
        )


def test_manual_compact_trigger_can_only_tighten_automatic_threshold():
    budget = derive_context_budget(
        4096,
        output_reserve_tokens=1024,
        safety_tokens=256,
        compact_trigger_ratio=0.8,
        compact_trigger_cap_tokens=2600,
    )

    assert budget.max_prompt_tokens == 2816
    assert budget.compact_trigger_tokens == 2252

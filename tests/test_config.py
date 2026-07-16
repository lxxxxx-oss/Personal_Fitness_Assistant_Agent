"""Configuration environment parsing regression tests."""

import pytest

from app.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_KNOWLEDGE_COLLECTION,
    DEFAULT_MEMORY_COLLECTION,
    Config,
)


def test_embedding_defaults_use_model_specific_collections(monkeypatch):
    for name in (
        "EMBEDDING_MODEL",
        "ROUTER_EMBEDDING_MODEL",
        "MILVUS_COLLECTION_NAME",
        "MILVUS_COLLECTION",
        "MEMORY_MILVUS_COLLECTION_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    config = Config()

    assert config.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.router_embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.milvus_collection_name == DEFAULT_KNOWLEDGE_COLLECTION
    assert config.memory_milvus_collection_name == DEFAULT_MEMORY_COLLECTION


def test_float_environment_values_are_parsed(monkeypatch):
    monkeypatch.setenv("MODEL_TEMPERATURE", "0.25")
    monkeypatch.setenv("RETRIEVER_THRESHOLD", "0.42")
    monkeypatch.setenv("RETRIEVER_CHUNK_CHARS", "256")
    monkeypatch.setenv("RETRIEVER_CHUNK_OVERLAP_CHARS", "32")
    monkeypatch.setenv("RETRIEVER_KNOWLEDGE_VERSION", "kb-2026-07")

    config = Config()

    assert config.model_temperature == 0.25
    assert config.retriever_threshold == 0.42
    assert config.retriever_chunk_chars == 256
    assert config.retriever_chunk_overlap_chars == 32
    assert config.retriever_knowledge_version == "kb-2026-07"


def test_invalid_float_environment_value_uses_default(monkeypatch):
    monkeypatch.setenv("MODEL_TOP_P", "not-a-number")

    assert Config().model_top_p == 0.95


def test_boolean_environment_values_are_real_booleans(monkeypatch):
    monkeypatch.setenv("RETRIEVER_FALLBACK_TO_MEMORY", "false")
    assert Config().retriever_fallback_to_memory is False

    monkeypatch.setenv("RETRIEVER_FALLBACK_TO_MEMORY", "yes")
    assert Config().retriever_fallback_to_memory is True


def test_conversation_summary_config_is_bounded_by_explicit_values(monkeypatch):
    monkeypatch.setenv("CONVERSATION_SUMMARY_ENABLED", "false")
    monkeypatch.setenv("CONVERSATION_SUMMARY_TRIGGER_CHARS", "2400")
    monkeypatch.setenv("CONVERSATION_SUMMARY_MAX_CHARS", "900")
    monkeypatch.setenv("CONVERSATION_SUMMARY_KEEP_RECENT_MESSAGES", "8")

    config = Config()

    assert config.conversation_summary_enabled is False
    assert config.conversation_summary_trigger_chars == 2400
    assert config.conversation_summary_max_chars == 900
    assert config.conversation_summary_keep_recent_messages == 8


def test_config_rejects_prompt_limits_that_cannot_compact_safely():
    with pytest.raises(ValueError, match="MAX_PROMPT_CHARS"):
        Config(
            context_compact_trigger_chars=1000,
            context_max_prompt_chars=1199,
        )


def test_config_rejects_compact_trigger_above_prompt_limit():
    with pytest.raises(ValueError, match="COMPACT_TRIGGER_CHARS"):
        Config(
            context_compact_trigger_chars=2000,
            context_max_prompt_chars=1500,
        )


def test_router_embedding_config_is_feature_flagged(monkeypatch):
    monkeypatch.setenv("ROUTER_EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("ROUTER_EMBEDDING_MODEL", "test-router-model")
    monkeypatch.setenv("ROUTER_EMBEDDING_MIN_CONFIDENCE", "0.7")
    monkeypatch.setenv("ROUTER_EMBEDDING_MIN_MARGIN", "0.08")

    config = Config()

    assert config.router_embedding_enabled is True
    assert config.router_embedding_model == "test-router-model"
    assert config.router_embedding_min_confidence == 0.7
    assert config.router_embedding_min_margin == 0.08

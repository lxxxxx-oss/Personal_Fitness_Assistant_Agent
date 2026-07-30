"""Configuration environment parsing regression tests."""

import json

import pytest

from app.config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_KNOWLEDGE_DB_PATH,
    DEFAULT_MEMORY_VECTOR_DB_PATH,
    Config,
)


def test_local_vector_store_defaults(monkeypatch):
    for name in (
        "EMBEDDING_MODEL",
        "ROUTER_EMBEDDING_MODEL",
        "RETRIEVER_BACKEND",
        "RETRIEVER_DB_PATH",
        "MEMORY_VECTOR_DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    config = Config()

    assert config.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.router_embedding_model == DEFAULT_EMBEDDING_MODEL
    assert config.retriever_backend == "sqlite_faiss"
    assert config.retriever_db_path == DEFAULT_KNOWLEDGE_DB_PATH
    assert config.memory_vector_db_path == DEFAULT_MEMORY_VECTOR_DB_PATH


def test_deepseek_api_key_supports_windows_compatibility_name(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DeepSeek", " compatibility-key ")

    config = Config()

    assert config.deepseek_api_key == "compatibility-key"


def test_standard_deepseek_api_key_takes_priority(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "standard-key")
    monkeypatch.setenv("DeepSeek", "compatibility-key")

    config = Config()

    assert config.deepseek_api_key == "standard-key"


def test_local_vector_store_environment_values(monkeypatch):
    monkeypatch.setenv("RETRIEVER_BACKEND", "memory")
    monkeypatch.setenv("RETRIEVER_DB_PATH", "tmp/custom-knowledge.db")
    monkeypatch.setenv("MEMORY_VECTOR_ENABLED", "true")
    monkeypatch.setenv("MEMORY_VECTOR_DB_PATH", "tmp/custom-memory.db")
    monkeypatch.setenv("RETRIEVER_TIMEOUT_SECONDS", "1.5")

    config = Config()

    assert config.retriever_backend == "memory"
    assert config.retriever_db_path == "tmp/custom-knowledge.db"
    assert config.memory_vector_enabled is True
    assert config.memory_vector_db_path == "tmp/custom-memory.db"
    assert config.retriever_timeout_seconds == 1.5


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


def test_hybrid_retrieval_defaults_and_environment_values(monkeypatch):
    monkeypatch.delenv("RETRIEVER_STRATEGY", raising=False)
    monkeypatch.delenv("RETRIEVER_CANDIDATE_K", raising=False)
    monkeypatch.delenv("RETRIEVER_RRF_K", raising=False)

    defaults = Config()
    assert defaults.retriever_strategy == "hybrid"
    assert defaults.retriever_candidate_k == 20
    assert defaults.retriever_rrf_k == 60

    monkeypatch.setenv("RETRIEVER_STRATEGY", "dense")
    monkeypatch.setenv("RETRIEVER_CANDIDATE_K", "12")
    monkeypatch.setenv("RETRIEVER_RRF_K", "50")
    configured = Config()
    assert configured.retriever_strategy == "dense"
    assert configured.retriever_candidate_k == 12
    assert configured.retriever_rrf_k == 50


def test_hybrid_retrieval_config_rejects_invalid_values():
    with pytest.raises(ValueError, match="RETRIEVER_STRATEGY"):
        Config(retriever_strategy="weighted")
    with pytest.raises(ValueError, match="RETRIEVER_CANDIDATE_K"):
        Config(retriever_candidate_k=101)


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
    monkeypatch.setenv("CONVERSATION_SUMMARY_TRIGGER_TOKENS", "700")
    monkeypatch.setenv("CONVERSATION_SUMMARY_MAX_TOKENS", "300")

    config = Config()

    assert config.conversation_summary_enabled is False
    assert config.conversation_summary_trigger_chars == 2400
    assert config.conversation_summary_max_chars == 900
    assert config.conversation_summary_trigger_tokens == 700
    assert config.conversation_summary_max_tokens == 300


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


def test_config_rejects_token_trigger_above_token_limit():
    with pytest.raises(ValueError, match="COMPACT_TRIGGER_TOKENS"):
        Config(
            context_compact_trigger_tokens=2000,
            context_max_prompt_tokens=1500,
        )


def test_context_budget_is_derived_from_local_model_metadata(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"max_position_embeddings": 8192}),
        encoding="utf-8",
    )

    config = Config(
        model_path=str(tmp_path),
        model_max_tokens=1024,
        context_safety_tokens=256,
        context_compact_trigger_ratio=0.8,
        context_compact_trigger_chars=0,
        context_max_prompt_chars=0,
        context_compact_trigger_tokens=0,
        context_max_prompt_tokens=0,
    )

    assert config.model_context_window_tokens == 8192
    assert config.model_context_window_source == "config.json:max_position_embeddings"
    assert config.context_max_prompt_tokens == 6912
    assert config.context_compact_trigger_tokens == 5529
    assert config.context_max_prompt_chars == 27648
    assert config.context_compact_trigger_chars == 22116


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

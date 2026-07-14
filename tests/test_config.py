"""Configuration environment parsing regression tests."""

from app.config import Config


def test_float_environment_values_are_parsed(monkeypatch):
    monkeypatch.setenv("MODEL_TEMPERATURE", "0.25")
    monkeypatch.setenv("RETRIEVER_THRESHOLD", "0.42")
    monkeypatch.setenv("RETRIEVER_CHUNK_CHARS", "256")
    monkeypatch.setenv("RETRIEVER_CHUNK_OVERLAP_CHARS", "32")

    config = Config()

    assert config.model_temperature == 0.25
    assert config.retriever_threshold == 0.42
    assert config.retriever_chunk_chars == 256
    assert config.retriever_chunk_overlap_chars == 32


def test_invalid_float_environment_value_uses_default(monkeypatch):
    monkeypatch.setenv("MODEL_TOP_P", "not-a-number")

    assert Config().model_top_p == 0.95


def test_boolean_environment_values_are_real_booleans(monkeypatch):
    monkeypatch.setenv("RETRIEVER_FALLBACK_TO_MEMORY", "false")
    assert Config().retriever_fallback_to_memory is False

    monkeypatch.setenv("RETRIEVER_FALLBACK_TO_MEMORY", "yes")
    assert Config().retriever_fallback_to_memory is True


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

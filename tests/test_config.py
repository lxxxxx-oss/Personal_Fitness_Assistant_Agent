"""Configuration environment parsing regression tests."""

from app.config import Config


def test_float_environment_values_are_parsed(monkeypatch):
    monkeypatch.setenv("MODEL_TEMPERATURE", "0.25")
    monkeypatch.setenv("RETRIEVER_THRESHOLD", "0.42")

    config = Config()

    assert config.model_temperature == 0.25
    assert config.retriever_threshold == 0.42


def test_invalid_float_environment_value_uses_default(monkeypatch):
    monkeypatch.setenv("MODEL_TOP_P", "not-a-number")

    assert Config().model_top_p == 0.95


def test_boolean_environment_values_are_real_booleans(monkeypatch):
    monkeypatch.setenv("RETRIEVER_FALLBACK_TO_MEMORY", "false")
    assert Config().retriever_fallback_to_memory is False

    monkeypatch.setenv("RETRIEVER_FALLBACK_TO_MEMORY", "yes")
    assert Config().retriever_fallback_to_memory is True

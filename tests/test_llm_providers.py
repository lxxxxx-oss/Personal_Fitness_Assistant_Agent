"""Tests for selectable local and external LLM providers."""

import json

import pytest

from app.config import config
from app.llm.deepseek import DeepSeekLLM
from app.llm.loader import LLMGenerationError, LLMLoader
from app.llm.providers import create_llm, list_models, resolve_model_id
from app.tools.types import ErrorCode


def _deepseek(*, api_key: str = "test-key") -> DeepSeekLLM:
    return DeepSeekLLM(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=10,
        max_tokens=128,
        temperature=0.3,
        top_p=0.9,
    )


def test_model_catalog_reports_availability_without_exposing_secret(monkeypatch):
    monkeypatch.setattr(config, "llm_mock", True)
    monkeypatch.setattr(config, "deepseek_api_key", "super-secret-key")
    monkeypatch.setattr(config, "llm_default_model", "deepseek-api")

    models = list_models()

    assert [item["id"] for item in models] == ["qwen-local", "deepseek-api"]
    assert all(item["available"] for item in models)
    assert next(item for item in models if item["default"])["id"] == "deepseek-api"
    assert "super-secret-key" not in json.dumps(models)


def test_provider_factory_keeps_one_generation_contract(monkeypatch):
    monkeypatch.setattr(config, "deepseek_api_key", "test-key")

    assert isinstance(create_llm("qwen-local"), LLMLoader)
    assert isinstance(create_llm("deepseek-api"), DeepSeekLLM)
    assert resolve_model_id(None) == config.llm_default_model

    with pytest.raises(LLMGenerationError) as exc_info:
        resolve_model_id("unknown-provider")
    assert exc_info.value.error_code == ErrorCode.INVALID_PARAM


def test_deepseek_requires_api_key_before_network_call():
    with pytest.raises(LLMGenerationError) as exc_info:
        _deepseek(api_key="").generate("hello")

    assert exc_info.value.error_code == ErrorCode.CONFIG_MISSING


def test_deepseek_generate_uses_openai_compatible_payload(monkeypatch):
    import app.llm.deepseek as deepseek_module

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "  API answer  "}}]}

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr(deepseek_module.httpx, "Client", FakeClient)

    result = _deepseek().generate("hello", max_new_tokens=64)

    assert result == "API answer"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured["payload"]["max_tokens"] == 64
    assert captured["payload"]["stream"] is False


def test_deepseek_stream_parses_sse_chunks(monkeypatch):
    import app.llm.deepseek as deepseek_module

    class FakeStreamResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"A"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"B"}}]}'
            yield "data: [DONE]"

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, *, headers, json):
            assert method == "POST"
            assert json["stream"] is True
            return FakeStreamResponse()

    monkeypatch.setattr(deepseek_module.httpx, "Client", FakeClient)

    assert list(_deepseek().generate_stream("hello")) == ["A", "B"]

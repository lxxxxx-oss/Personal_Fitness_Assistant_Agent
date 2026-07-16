"""LLM加载器测试."""
import json
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor

import pytest
import app.llm.loader as loader_module
from app.llm.loader import LLMGenerationError, LLMLoader, _mock_response
from app.tools.types import ErrorCode


@pytest.fixture(autouse=True)
def reset_shared_model_cache():
    loader_module._MODEL_CACHE.clear()
    yield
    loader_module._MODEL_CACHE.clear()


def _install_fake_model_runtime(monkeypatch, model_factory):
    fake_torch = types.ModuleType("torch")
    fake_torch.float32 = "float32"
    fake_torch.bfloat16 = "bfloat16"
    fake_torch.cuda = types.SimpleNamespace(
        is_available=lambda: False,
        empty_cache=lambda: None,
    )

    tokenizer = object()
    tokenizer_loader = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: tokenizer
    )
    model_loader = types.SimpleNamespace(from_pretrained=model_factory)

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoTokenizer = tokenizer_loader
    fake_transformers.AutoModelForCausalLM = model_loader

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    return tokenizer


class TestLLMLoader:
    def test_prompt_contract_rejects_empty_input(self):
        with pytest.raises(LLMGenerationError) as exc_info:
            LLMLoader._validate_prompt("  ")

        assert exc_info.value.error_code == ErrorCode.INVALID_PARAM
        assert "empty or invalid" in exc_info.value.public_message

    def test_prompt_contract_uses_configured_limit(self, monkeypatch):
        from app.config import config

        monkeypatch.setattr(config, "context_max_prompt_chars", 1200)
        with pytest.raises(LLMGenerationError) as exc_info:
            LLMLoader._validate_prompt("x" * 1201)

        assert exc_info.value.error_code == ErrorCode.INVALID_PARAM
        assert "configured size limit" in exc_info.value.public_message

    def test_loader_initializes_with_config(self):
        from app.config import config
        loader = LLMLoader(
            model_path=config.model_path,
            device="cpu",
            max_tokens=64,
            temperature=0.6,
            top_p=0.95,
        )
        assert loader.model_path == config.model_path
        assert loader.device == "cpu"

    def test_generate_returns_string(self):
        """注意: 此测试需要模型文件存在,在不满足条件时skip."""
        import os
        loader = LLMLoader(model_path="skipped", device="cpu")
        if not os.path.exists(loader.model_path):
            pytest.skip("Model file not available")
        result = loader.generate("你好", max_new_tokens=16)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_mock_recipe_response_uses_tool_payload(self):
        payload = {
            "name": "蛋炒饭",
            "ingredients": [
                {"name": "米饭", "text_quantity": "米饭 1碗"},
                {"name": "鸡蛋", "text_quantity": "鸡蛋 2个"},
            ],
            "steps": ["先炒鸡蛋", "加入米饭翻炒", "加盐调味"],
        }
        prompt = (
            "# 工具返回数据\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "# 用户问题\n蛋炒饭怎么做\n"
        )

        result = _mock_response(prompt)

        assert "蛋炒饭" in result
        assert "米饭" in result
        assert "番茄炒蛋" not in result

    def test_mock_recipe_response_ignores_conversation_summary_block(self):
        payload = {
            "name": "番茄炒蛋",
            "ingredients": [
                {"name": "番茄", "text_quantity": "番茄 2个"},
                {"name": "鸡蛋", "text_quantity": "鸡蛋 3个"},
            ],
            "steps": ["鸡蛋打散炒熟", "番茄炒出汁", "倒回鸡蛋调味"],
        }
        prompt = (
            "# 工具返回数据\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "# 当前会话摘要\n"
            "用户正在测试 MCP 菜谱演示。\n\n"
            "# 用户问题\n菜谱：番茄炒蛋怎么做？\n"
        )

        result = _mock_response(prompt)

        assert "番茄炒蛋" in result
        assert "番茄 2个" in result
        assert "当前会话摘要" not in result
        assert "# 用户问题" not in result

    def test_mock_recipe_response_unwraps_mcp_text_content(self):
        recipe = {
            "name": "番茄炒蛋",
            "ingredients": [
                {"name": "番茄", "text_quantity": "番茄 2个"},
                {"name": "鸡蛋", "text_quantity": "鸡蛋 3个"},
            ],
            "steps": ["鸡蛋打散炒熟", "番茄炒出汁", "倒回鸡蛋调味"],
        }
        payload = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(recipe, ensure_ascii=False),
                }
            ]
        }
        prompt = (
            "# 工具返回数据\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "# 当前会话摘要\n"
            "用户正在测试 MCP 菜谱演示。\n\n"
            "# 用户问题\n菜谱：番茄炒蛋怎么做？\n"
        )

        result = _mock_response(prompt)

        assert "番茄炒蛋" in result
        assert "鸡蛋 3个" in result
        assert "工具返回数据" not in result
        assert "当前会话摘要" not in result

    def test_multiple_loaders_reuse_one_process_model(
        self,
        monkeypatch,
        tmp_path,
    ):
        from app.config import config

        monkeypatch.setattr(config, "llm_mock", False)
        load_count = 0

        class FakeModel:
            def to(self, device):
                self.device = device
                return self

            def eval(self):
                return self

        def load_model(*args, **kwargs):
            nonlocal load_count
            load_count += 1
            return FakeModel()

        tokenizer = _install_fake_model_runtime(monkeypatch, load_model)
        loader_a = LLMLoader(model_path=str(tmp_path), device="cpu")
        loader_b = LLMLoader(model_path=str(tmp_path), device="cpu")

        result_a = loader_a._ensure_loaded()
        result_b = loader_b._ensure_loaded()

        assert result_a.ok
        assert result_b.ok
        assert load_count == 1
        assert loader_a._model is loader_b._model
        assert loader_a._tokenizer is tokenizer
        assert loader_b._tokenizer is tokenizer
        assert len(loader_module._MODEL_CACHE) == 1

    def test_failed_model_load_does_not_pollute_shared_cache(
        self,
        monkeypatch,
        tmp_path,
    ):
        from app.config import config

        monkeypatch.setattr(config, "llm_mock", False)
        load_count = 0

        def fail_model_load(*args, **kwargs):
            nonlocal load_count
            load_count += 1
            raise MemoryError("simulated out of memory")

        _install_fake_model_runtime(monkeypatch, fail_model_load)
        loader_a = LLMLoader(model_path=str(tmp_path), device="cpu")
        loader_b = LLMLoader(model_path=str(tmp_path), device="cpu")

        result_a = loader_a._ensure_loaded()
        result_b = loader_b._ensure_loaded()

        assert not result_a.ok
        assert not result_b.ok
        assert load_count == 2
        assert loader_a._model is None
        assert loader_b._model is None
        assert loader_module._MODEL_CACHE == {}

    def test_concurrent_first_load_only_allocates_one_model(
        self,
        monkeypatch,
        tmp_path,
    ):
        from app.config import config

        monkeypatch.setattr(config, "llm_mock", False)
        load_count = 0

        class FakeModel:
            def to(self, device):
                return self

            def eval(self):
                return self

        def load_model(*args, **kwargs):
            nonlocal load_count
            load_count += 1
            time.sleep(0.02)
            return FakeModel()

        _install_fake_model_runtime(monkeypatch, load_model)
        loaders = [
            LLMLoader(model_path=str(tmp_path), device="cpu")
            for _ in range(8)
        ]

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda loader: loader._ensure_loaded(), loaders))

        assert all(result.ok for result in results)
        assert load_count == 1
        assert len({id(loader._model) for loader in loaders}) == 1
        assert len(loader_module._MODEL_CACHE) == 1

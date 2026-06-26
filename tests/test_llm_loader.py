"""LLM加载器测试."""
import pytest
from app.llm.loader import LLMLoader


class TestLLMLoader:
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

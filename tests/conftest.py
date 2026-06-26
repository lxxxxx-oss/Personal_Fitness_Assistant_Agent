"""Pytest conftest — global fixtures for the fitness assistant tests."""
import sys
import types
import numpy as np
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture(autouse=True)
def mock_sentence_transformer():
    """Mock SentenceTransformer globally to avoid network downloads in tests."""
    mock_st = MagicMock()

    def fake_encode(texts, normalize_embeddings=False):
        if isinstance(texts, str):
            texts = [texts]
        vecs = np.zeros((len(texts), 384), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = hash(t) % (2**31)
            rng = np.random.RandomState(seed)
            vecs[i] = rng.rand(384).astype(np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms < 1e-8] = 1.0
            vecs = vecs / norms
        return vecs

    mock_st.encode = fake_encode

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = MagicMock(return_value=mock_st)
    sys.modules.setdefault("sentence_transformers", fake_module)

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_st):
        yield mock_st


@pytest.fixture(autouse=True)
def mock_llm_generation(monkeypatch):
    """Mock local LLM generation so tests do not require model files."""
    from app.llm.loader import LLMLoader

    def fake_generate(self, prompt, *args, **kwargs):
        return "Mock LLM response"

    def fake_generate_stream(self, prompt, *args, **kwargs):
        yield "Mock"
        yield " stream"
        yield " response"

    monkeypatch.setattr(LLMLoader, "generate", fake_generate)
    monkeypatch.setattr(LLMLoader, "generate_stream", fake_generate_stream)

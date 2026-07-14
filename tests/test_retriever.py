"""Vector retriever tests using mock embeddings."""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from app.tools.retriever import (
    MemoryRetriever,
    _build_chunk_entries,
    _chinese_sentence_split,
)


class TestChineseSentenceSplit:
    def test_split_by_newline(self):
        text = "First sentence.\nSecond sentence.\n"
        chunks = _chinese_sentence_split(text)
        assert len(chunks) >= 1

    def test_single_sentence(self):
        text = "One complete sentence."
        chunks = _chinese_sentence_split(text)
        assert len(chunks) == 1

    def test_empty_returns_original(self):
        text = ""
        chunks = _chinese_sentence_split(text)
        assert chunks == [""]

    def test_overlong_sentence_is_split_by_max_chunk_chars(self):
        text = "深蹲" * 120
        chunks = _chinese_sentence_split(text, max_chunk_chars=50)

        assert len(chunks) > 1
        assert all(len(chunk) <= 50 for chunk in chunks)
        assert "".join(chunks) == text

    def test_overlong_sentence_supports_overlap(self):
        text = "abcdefghijklmnopqrstuvwxyz"
        chunks = _chinese_sentence_split(
            text,
            max_chunk_chars=10,
            overlap_chars=2,
        )

        assert chunks[:2] == ["abcdefghij", "ijklmnopqr"]
        assert all(len(chunk) <= 10 for chunk in chunks)


class TestMemoryRetriever:
    @pytest.fixture
    def mock_encoder(self):
        """Create a mock encoder that returns fixed-dimension vectors."""
        mock = MagicMock()
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
        mock.encode = fake_encode
        return mock

    @pytest.fixture
    def retriever(self, mock_encoder):
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_encoder,
        ):
            r = MemoryRetriever(embedding_model="mock-model")
            # Bypass lazy loading
            r._encoder = mock_encoder
            return r

    @pytest.fixture
    def sample_docs(self):
        return [
            "Squat is an effective lower body exercise targeting quads and glutes.",
            "During cutting, reduce carb intake and increase protein ratio.",
            "Keep your back straight during deadlifts to avoid injury.",
        ]

    def test_add_and_search(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        result = retriever.search("how to squat", top_k=2, threshold=0.0)
        assert result.ok
        assert len(result.data) >= 1
        assert all("content" in r for r in result.data)

    def test_failed_encoder_load_is_not_retried_for_every_search(self, sample_docs):
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=OSError("model unavailable"),
        ) as loader:
            retriever = MemoryRetriever(embedding_model="missing-model")
            retriever.add_documents(sample_docs)
            first = retriever.search("squat", top_k=2, threshold=0.0)
            second = retriever.search("deadlift", top_k=2, threshold=0.0)

        assert first.ok and first.meta["mode"] == "keyword"
        assert second.ok and second.meta["mode"] == "keyword"
        assert first.meta["embedding_model"] == "missing-model"
        assert "model unavailable" in first.meta["fallback_reason"]
        assert loader.call_count == 1

    def test_search_returns_scores(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        result = retriever.search("diet and nutrition", top_k=3)
        assert result.ok
        for r in result.data:
            assert "score" in r
            assert "content" in r
            assert 0.0 <= r["score"] <= 1.0

    def test_search_with_threshold(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        result = retriever.search("yoga meditation", top_k=3, threshold=0.99)
        assert result.ok
        assert len(result.data) <= 1

    def test_clear(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        retriever.clear()
        result = retriever.search("squat", top_k=5)
        assert result.ok
        assert len(result.data) == 0

    def test_document_count(self, retriever, sample_docs):
        assert retriever.document_count == 0
        retriever.add_documents(sample_docs)
        assert retriever.document_count >= 1

    def test_add_documents_returns_manifest_with_versioned_chunk_ids(
        self,
        retriever,
    ):
        result = retriever.add_documents(
            ["深蹲训练需要保持核心稳定。"],
            sources=["fitness.txt"],
        )
        expected_entries = _build_chunk_entries(
            ["深蹲训练需要保持核心稳定。"],
            ["fitness.txt"],
        )

        assert result.ok
        assert result.data["manifest"]["chunk_count"] == 1
        assert result.data["manifest"]["sources"][0]["source"] == "fitness.txt"
        assert result.data["manifest"]["sources"][0]["chunk_ids"] == [
            expected_entries[0]["id"]
        ]

    def test_reingesting_same_source_replaces_stale_chunks(self, retriever):
        first = retriever.add_documents(
            ["深蹲" * 300],
            sources=["fitness.txt"],
        )
        second = retriever.add_documents(
            ["深蹲" * 10],
            sources=["fitness.txt"],
        )

        assert first.ok
        assert second.ok
        assert second.data["removed"] >= 1
        assert retriever.document_count == 1
        assert retriever._documents == ["深蹲" * 10]

"""Vector retriever tests using mock embeddings."""
import sys
import types

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from app.tools.retriever import (
    MemoryRetriever,
    MilvusRetriever,
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


class FakeSchema:
    def __init__(self):
        self.fields = []

    def add_field(self, **kwargs):
        self.fields.append(kwargs)


class FakeIndexParams:
    def __init__(self):
        self.indexes = []

    def add_index(self, **kwargs):
        self.indexes.append(kwargs)


class FakeMilvusClient:
    def __init__(self, *args, **kwargs):
        self.collections = set()
        self.rows = []
        self.created_schema = None
        self.created_indexes = None

    def has_collection(self, collection_name):
        return collection_name in self.collections

    def create_schema(self, **kwargs):
        return FakeSchema()

    def prepare_index_params(self):
        return FakeIndexParams()

    def create_collection(self, collection_name, schema, index_params):
        self.collections.add(collection_name)
        self.created_schema = schema
        self.created_indexes = index_params

    def upsert(self, collection_name, data):
        self.collections.add(collection_name)
        self.rows.extend(data)

    def flush(self, collection_name):
        return None

    def load_collection(self, collection_name):
        return None

    def search(
        self,
        collection_name,
        data,
        anns_field,
        search_params,
        limit,
        output_fields,
    ):
        hits = []
        for row in self.rows[:limit]:
            hits.append({
                "id": row["id"],
                "distance": 0.91,
                "entity": {
                    "content": row["content"],
                    "source": row["source"],
                },
            })
        return [hits]

    def drop_collection(self, collection_name):
        self.collections.discard(collection_name)
        self.rows = []


class TestMilvusRetriever:
    @pytest.fixture(autouse=True)
    def fake_pymilvus(self, monkeypatch):
        fake_datatype = types.SimpleNamespace(
            VARCHAR="VARCHAR",
            FLOAT_VECTOR="FLOAT_VECTOR",
        )
        fake_module = types.SimpleNamespace(
            MilvusClient=FakeMilvusClient,
            DataType=fake_datatype,
        )
        monkeypatch.setitem(sys.modules, "pymilvus", fake_module)

    @pytest.fixture
    def mock_encoder(self):
        mock = MagicMock()

        def fake_encode(texts, normalize_embeddings=False):
            if isinstance(texts, str):
                texts = [texts]
            vecs = np.ones((len(texts), 4), dtype=np.float32)
            if normalize_embeddings:
                vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
            return vecs

        mock.encode = fake_encode
        return mock

    def test_add_documents_creates_collection_and_upserts(self, mock_encoder):
        retriever = MilvusRetriever(
            embedding_model="mock-model",
            collection_name="test_collection",
        )
        retriever._encoder = mock_encoder
        retriever.add_documents(["深蹲可以训练下肢力量。"], source="fitness.txt")

        assert retriever.document_count == 1
        assert retriever._client.has_collection("test_collection")
        assert retriever._client.rows[0]["source"] == "fitness.txt"
        assert "embedding" in retriever._client.rows[0]

    def test_search_returns_tool_result_shape(self, mock_encoder):
        retriever = MilvusRetriever(
            embedding_model="mock-model",
            collection_name="test_collection",
        )
        retriever._encoder = mock_encoder
        retriever.add_documents(["蛋白质有助于肌肉修复。"], source="nutrition.txt")

        result = retriever.search("蛋白质有什么作用", top_k=1, threshold=0.3)

        assert result.ok
        assert result.meta["mode"] == "milvus"
        assert result.data[0]["content"] == "蛋白质有助于肌肉修复。"
        assert result.data[0]["source"] == "nutrition.txt"
        assert result.data[0]["score"] == 0.91

    def test_fallback_to_memory_when_milvus_unavailable(self, mock_encoder):
        retriever = MilvusRetriever(embedding_model="mock-model")
        retriever._encoder = mock_encoder
        retriever._ensure_client = MagicMock(return_value=False)
        retriever._disabled_reason = "Cannot connect to Milvus"
        retriever.add_documents(["深蹲训练股四头肌。"], source="fitness.txt")

        result = retriever.search("深蹲", top_k=1, threshold=0.0)

        assert result.ok
        assert result.meta["backend"] == "milvus_fallback"
        assert len(result.data) == 1

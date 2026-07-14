"""Milvus RAG retriever contract tests without a live Milvus service."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from app.tools.retriever import (
    MemoryRetriever,
    MilvusRetriever,
    ResilientRetriever,
    _build_chunk_entries,
)
from app.tools.types import ErrorCode, ToolResult


class FakeDataType:
    INT64 = "INT64"
    FLOAT_VECTOR = "FLOAT_VECTOR"
    VARCHAR = "VARCHAR"


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


class FakeMilvusClientType:
    @staticmethod
    def create_schema(**kwargs):
        return FakeSchema()

    @staticmethod
    def prepare_index_params():
        return FakeIndexParams()


class FakeMilvusClient:
    def __init__(self):
        self.collection_exists = False
        self.schema = None
        self.index_params = None
        self.rows = []
        self.search_results = [[]]
        self.loaded = False
        self.flushed = False
        self.closed = False
        self.deleted_ids = []

    def has_collection(self, collection_name):
        return self.collection_exists

    def describe_collection(self, collection_name):
        vector = next(
            field for field in self.schema.fields if field["field_name"] == "vector"
        )
        return {
            "fields": [
                {
                    "name": "vector",
                    "params": {"dim": vector["dim"]},
                }
            ]
        }

    def create_collection(self, collection_name, schema, consistency_level):
        self.collection_exists = True
        self.schema = schema
        self.consistency_level = consistency_level

    def create_index(self, collection_name, index_params):
        self.index_params = index_params

    def list_indexes(self, collection_name):
        return ["vector_index"] if self.index_params is not None else []

    def load_collection(self, collection_name):
        self.loaded = True

    def upsert(self, collection_name, data):
        by_id = {row["id"]: row for row in self.rows}
        by_id.update({row["id"]: row for row in data})
        self.rows = list(by_id.values())
        return {"primary_keys": [row["id"] for row in data]}

    def delete(self, collection_name, ids):
        self.deleted_ids.extend(ids)
        remove_ids = set(ids)
        before = len(self.rows)
        self.rows = [row for row in self.rows if row["id"] not in remove_ids]
        return {"delete_count": before - len(self.rows)}

    def flush(self, collection_name):
        self.flushed = True

    def search(self, **kwargs):
        self.last_search = kwargs
        return self.search_results

    def get_collection_stats(self, collection_name):
        return {"row_count": len(self.rows)}

    def drop_collection(self, collection_name):
        self.collection_exists = False
        self.rows = []

    def close(self):
        self.closed = True


def make_encoder(dimension=4):
    encoder = MagicMock()

    def encode(texts, normalize_embeddings=False):
        vectors = np.ones((len(texts), dimension), dtype=np.float32)
        if normalize_embeddings:
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors

    encoder.encode = encode
    return encoder


def make_retriever():
    retriever = MilvusRetriever(
        uri="http://milvus:19530",
        collection_name="fitness_knowledge",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        nlist=32,
        nprobe=4,
    )
    client = FakeMilvusClient()
    retriever._client = client
    retriever._milvus_client_type = FakeMilvusClientType
    retriever._data_type = FakeDataType
    retriever._encoder = make_encoder()
    return retriever, client


def test_milvus_retriever_rejects_unsafe_collection_name():
    with pytest.raises(ValueError):
        MilvusRetriever(
            uri="http://milvus:19530",
            collection_name="bad-name;drop",
        )


def test_add_documents_creates_collection_index_and_upserts():
    retriever, client = make_retriever()

    result = retriever.add_documents(
        ["深蹲训练需要保持核心稳定。"],
        sources=["fitness.txt"],
    )

    assert result.ok
    assert result.meta["backend"] == "milvus"
    assert result.meta["dimension"] == 4
    assert client.collection_exists
    assert client.loaded
    assert client.flushed
    assert client.consistency_level == "Strong"
    assert client.index_params.indexes == [
        {
            "field_name": "vector",
            "index_name": "vector_index",
            "index_type": "IVF_FLAT",
            "metric_type": "COSINE",
            "params": {"nlist": 32},
        }
    ]
    expected_entries = _build_chunk_entries(
        ["深蹲训练需要保持核心稳定。"],
        ["fitness.txt"],
    )
    assert client.rows[0]["source"] == "fitness.txt"
    assert client.rows[0]["id"] == expected_entries[0]["id"]
    assert result.data["manifest"]["sources"][0]["source"] == "fitness.txt"
    assert result.data["manifest"]["sources"][0]["chunk_ids"] == [
        expected_entries[0]["id"]
    ]
    assert result.data["removed"] == 0


def test_upsert_is_idempotent_for_same_chunk():
    retriever, client = make_retriever()
    docs = ["渐进超负荷需要逐步增加训练刺激。"]

    assert retriever.add_documents(docs).ok
    second = retriever.add_documents(docs)

    assert len(client.rows) == 1
    assert second.data["removed"] == 1
    assert client.deleted_ids


def test_reingesting_same_source_removes_stale_chunks():
    retriever, client = make_retriever()

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
    assert second.data["removed"] == first.data["upserted"]
    assert len(client.rows) == 1
    assert client.rows[0]["content"] == "深蹲" * 10


def test_search_returns_thresholded_structured_results():
    retriever, client = make_retriever()
    assert retriever.add_documents(["占位知识"]).ok
    client.search_results = [[
        {
            "id": 11,
            "distance": 0.91,
            "entity": {"content": "高相关知识", "source": "a.txt"},
        },
        {
            "id": 12,
            "distance": 0.20,
            "entity": {"content": "低相关知识", "source": "b.txt"},
        },
    ]]

    result = retriever.search("如何深蹲", top_k=5, threshold=0.5)

    assert result.ok
    assert result.data == [
        {
            "content": "高相关知识",
            "score": 0.91,
            "index": 11,
            "source": "a.txt",
        }
    ]
    assert client.last_search["search_params"] == {
        "metric_type": "COSINE",
        "params": {"nprobe": 4},
    }


def test_existing_collection_dimension_mismatch_is_actionable():
    retriever, client = make_retriever()
    client.collection_exists = True
    client.schema = FakeSchema()
    client.schema.add_field(field_name="vector", datatype="FLOAT_VECTOR", dim=8)

    result = retriever.add_documents(["测试知识"])

    assert not result.ok
    assert result.error_code == ErrorCode.INVALID_PARAM
    assert "dimension 8" in result.error_message


class FailingPrimary:
    document_count = 0

    def add_documents(self, docs, sources=None):
        return ToolResult.fail(ErrorCode.NETWORK_ERROR, "connection refused")

    def search(self, query, top_k=5, threshold=0.3):
        return ToolResult.fail(ErrorCode.NETWORK_ERROR, "connection refused")

    def clear(self):
        return ToolResult.fail(ErrorCode.NETWORK_ERROR, "connection refused")

    def close(self):
        return None


class FlakyPrimary:
    document_count = 0

    def __init__(self):
        self.fail = False

    def add_documents(self, docs, sources=None):
        if self.fail:
            return ToolResult.fail(ErrorCode.NETWORK_ERROR, "connection refused")
        return ToolResult.ok(data={"upserted": len(docs)}, backend="milvus")

    def search(self, query, top_k=5, threshold=0.3):
        if self.fail:
            return ToolResult.fail(ErrorCode.NETWORK_ERROR, "connection refused")
        return ToolResult.ok(data=[], backend="milvus")

    def clear(self):
        return ToolResult.ok(data={"cleared": True}, backend="milvus")

    def close(self):
        return None


def test_resilient_retriever_hydrates_memory_after_milvus_failure():
    fallback = MemoryRetriever(embedding_model="mock")
    fallback._encoder = make_encoder()
    retriever = ResilientRetriever(
        primary=FailingPrimary(),
        fallback=fallback,
        fallback_enabled=True,
    )

    add_result = retriever.add_documents(
        ["深蹲训练需要保持核心稳定。"],
        sources=["fitness.txt"],
    )
    search_result = retriever.search("深蹲", top_k=1, threshold=0.0)

    assert add_result.ok
    assert add_result.meta["fallback_from"] == "milvus"
    assert search_result.ok
    assert search_result.data[0]["source"] == "fitness.txt"
    assert search_result.meta["backend"] == "memory"
    assert "connection refused" in search_result.meta["fallback_reason"]


def test_resilient_retriever_hydrates_latest_source_only_after_milvus_failure():
    primary = FlakyPrimary()
    fallback = MemoryRetriever(embedding_model="mock")
    fallback._encoder = make_encoder()
    retriever = ResilientRetriever(
        primary=primary,
        fallback=fallback,
        fallback_enabled=True,
    )

    assert retriever.add_documents(["旧知识"], sources=["fitness.txt"]).ok
    assert retriever.add_documents(["新知识"], sources=["fitness.txt"]).ok
    primary.fail = True

    result = retriever.search("新知识", top_k=5, threshold=0.0)

    assert result.ok
    assert fallback.document_count == 1
    assert fallback._documents == ["新知识"]

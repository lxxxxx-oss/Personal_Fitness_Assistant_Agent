"""SQLite persistence and FAISS dense-retrieval contract tests."""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

pytest.importorskip("faiss")

from app.tools.types import ErrorCode, ToolResult
from app.tools.retriever import ResilientRetriever, SQLiteFaissRetriever


class DeterministicEncoder:
    """Tiny offline encoder whose dimensions represent stable test topics."""

    def encode(self, texts, normalize_embeddings=True):
        rows = []
        for text in texts:
            lowered = str(text).lower()
            vector = np.asarray(
                [
                    3.0 if any(word in lowered for word in ("深蹲", "腿部", "squat")) else 0.1,
                    3.0 if any(word in lowered for word in ("蛋白", "饮食", "protein")) else 0.1,
                    3.0 if any(word in lowered for word in ("睡眠", "恢复", "sleep")) else 0.1,
                    1.0,
                ],
                dtype=np.float32,
            )
            if normalize_embeddings:
                vector = vector / np.linalg.norm(vector)
            rows.append(vector)
        return np.asarray(rows, dtype=np.float32)


def build_retriever(db_path, *, model="test-encoder-v1"):
    return SQLiteFaissRetriever(
        db_path=str(db_path),
        embedding_model=model,
        encoder=DeterministicEncoder(),
    )


def test_sqlite_store_survives_reopen_and_faiss_index_is_rebuilt(tmp_path):
    db_path = tmp_path / "knowledge.db"
    first = build_retriever(db_path)
    added = first.add_documents(
        ["深蹲主要训练腿部肌群。", "蛋白质有助于训练后的饮食恢复。"],
        sources=["strength.md", "nutrition.md"],
    )

    assert added.ok
    assert added.meta["backend"] == "sqlite_faiss"
    assert added.meta["index_type"] == "IndexFlatIP"
    assert first.document_count == 2
    first.close()

    reopened = build_retriever(db_path)
    result = reopened.search("深蹲怎么练腿", top_k=1, threshold=0.0)

    assert result.ok
    assert result.data[0]["source"] == "strength.md"
    assert "腿部" in result.data[0]["content"]
    assert result.meta["metric_type"] == "COSINE"
    assert reopened.document_count == 2
    reopened.close()


def test_sqlite_faiss_search_can_skip_score_threshold(tmp_path):
    retriever = build_retriever(tmp_path / "knowledge.db")
    assert retriever.add_documents(
        ["深蹲训练腿部。", "蛋白质支持恢复。", "睡眠有助于恢复。"],
        sources=["strength.md", "nutrition.md", "sleep.md"],
    ).ok

    result = retriever.search("完全无关的查询", top_k=3, threshold=None)

    assert result.ok
    assert len(result.data) == 3


def test_same_source_is_atomically_replaced_instead_of_accumulating_stale_chunks(tmp_path):
    retriever = build_retriever(tmp_path / "knowledge.db")
    first = retriever.add_documents(
        ["深蹲训练腿部。\n\n旧版本还包含睡眠建议。"],
        sources=["guide.md"],
    )
    replacement = retriever.add_documents(
        ["蛋白质摄入应结合体重与训练目标。"],
        sources=["guide.md"],
    )

    assert first.ok and replacement.ok
    assert replacement.data["removed"] == first.data["upserted"]
    assert retriever.document_count == replacement.data["upserted"]
    result = retriever.search("蛋白质饮食", top_k=5, threshold=0.0)
    assert result.ok
    assert all("旧版本" not in item["content"] for item in result.data)


def test_delete_sources_removes_only_requested_vectors(tmp_path):
    retriever = build_retriever(tmp_path / "knowledge.db")
    assert retriever.add_documents(
        ["深蹲训练腿部。", "蛋白质支持恢复。"],
        sources=["memory-a", "memory-b"],
    ).ok

    deleted = retriever.delete_sources(["memory-a"])
    result = retriever.search("深蹲", top_k=5, threshold=0.0)

    assert deleted.ok
    assert deleted.data == {"deleted": 1, "sources": ["memory-a"]}
    assert retriever.document_count == 1
    assert all(item["source"] != "memory-a" for item in result.data)


def test_persisted_embedding_model_mismatch_is_a_configuration_conflict(tmp_path):
    db_path = tmp_path / "knowledge.db"
    original = build_retriever(db_path, model="test-encoder-v1")
    assert original.add_documents(["深蹲训练。"], sources=["guide.md"]).ok
    original.close()

    incompatible = build_retriever(db_path, model="test-encoder-v2")
    result = incompatible.add_documents(["蛋白质饮食。"], sources=["food.md"])

    assert not result.ok
    assert result.error_code == ErrorCode.CONFIG_CONFLICT
    assert "test-encoder-v1" in result.error_message
    assert "test-encoder-v2" in result.error_message


def test_store_records_chunks_metadata_and_float32_embeddings_in_sqlite(tmp_path):
    db_path = tmp_path / "knowledge.db"
    retriever = build_retriever(db_path)
    assert retriever.add_documents(
        ["# 动作\n\n## 深蹲\n\n深蹲训练腿部。"],
        sources=["guide.md"],
    ).ok
    retriever.close()

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT source, section_path, embedding_dim, length(embedding) "
            "FROM knowledge_chunks"
        ).fetchone()
        metadata = dict(connection.execute("SELECT key, value FROM vector_store_meta"))

    assert row[0] == "guide.md"
    assert "深蹲" in row[1]
    assert row[2] == 4
    assert row[3] == 4 * 4
    assert metadata == {
        "embedding_model": "test-encoder-v1",
        "embedding_dimension": "4",
        "index_type": "IndexFlatIP",
    }


def test_invalid_inputs_return_tool_errors_without_touching_the_database(tmp_path):
    db_path = tmp_path / "knowledge.db"
    retriever = build_retriever(db_path)

    invalid_docs = retriever.add_documents("not-a-list")
    invalid_top_k = retriever.search("深蹲", top_k=0)
    empty_query = retriever.search("   ")

    assert invalid_docs.error_code == ErrorCode.INVALID_PARAM
    assert invalid_top_k.error_code == ErrorCode.INVALID_PARAM
    assert empty_query.ok and empty_query.data == []
    assert not db_path.exists()


class FailingLocalRetriever:
    backend_name = "sqlite_faiss"
    document_count = 0

    def add_documents(self, docs, sources=None):
        return ToolResult.fail(ErrorCode.INTERNAL_ERROR, "local index unavailable")

    def search(self, query, top_k=5, threshold=0.3):
        return ToolResult.fail(ErrorCode.INTERNAL_ERROR, "local index unavailable")

    def clear(self):
        return ToolResult.fail(ErrorCode.INTERNAL_ERROR, "local index unavailable")

    def close(self):
        return None


def test_resilient_retriever_reports_sqlite_faiss_as_fallback_source():
    fallback = build_retriever(":memory:")
    resilient = ResilientRetriever(FailingLocalRetriever(), fallback)

    added = resilient.add_documents(["深蹲训练腿部。"], sources=["guide.md"])
    result = resilient.search("深蹲", top_k=1, threshold=0.0)

    assert added.ok and result.ok
    assert added.meta["fallback_from"] == "sqlite_faiss"
    assert result.meta["fallback_from"] == "sqlite_faiss"
    assert result.meta["degraded"] is True

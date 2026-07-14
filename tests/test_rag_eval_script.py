import json
from pathlib import Path

import pytest

from app.tools.types import ToolResult
from scripts.eval_rag import evaluate, load_knowledge, load_rows


DATASET_PATH = Path("data/eval/rag_eval.jsonl")


class StubRetriever:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query

    def search(self, query, top_k, threshold):
        return ToolResult.ok(
            data=self.results_by_query.get(query, [])[:top_k],
            mode="embedding",
        )


class IngestionStub:
    def add_documents(self, documents, sources):
        return ToolResult.ok(
            data={"upserted": len(documents)},
            backend="memory",
        )


def test_rag_eval_dataset_has_answerable_and_no_answer_cases():
    rows = load_rows(DATASET_PATH)

    assert len(rows) == 15
    assert any(row["answerable"] for row in rows)
    assert any(not row["answerable"] for row in rows)
    assert {row["category"] for row in rows} >= {
        "guideline",
        "exercise",
        "nutrition",
        "no_answer",
    }


def test_evaluate_calculates_retrieval_and_rejection_metrics():
    rows = [
        {
            "id": "hit_at_two",
            "query": "q1",
            "answerable": True,
            "expected_sources": ["gold.txt"],
            "relevant_contains": ["正确事实"],
        },
        {
            "id": "miss",
            "query": "q2",
            "answerable": True,
            "expected_sources": ["gold.txt"],
            "relevant_contains": ["正确事实"],
        },
        {
            "id": "rejected",
            "query": "q3",
            "answerable": False,
            "expected_sources": [],
            "relevant_contains": [],
        },
    ]
    retriever = StubRetriever(
        {
            "q1": [
                {"source": "other.txt", "content": "干扰", "score": 0.9},
                {"source": "gold.txt", "content": "这里有正确事实", "score": 0.8},
            ],
            "q2": [
                {"source": "gold.txt", "content": "同源但片段无关", "score": 0.7}
            ],
            "q3": [],
        }
    )

    result = evaluate(rows, retriever, top_k=3, threshold=0.5)

    assert result["recall_at_k"] == 0.5
    assert result["mrr"] == 0.25
    assert result["source_hit_rate"] == 1.0
    assert result["no_answer_rejection_rate"] == 1.0
    assert result["mode_counts"] == {"embedding": 3}
    assert {case["id"] for case in result["failures"]} == {"miss"}


def test_load_rows_rejects_answerable_case_without_gold_evidence(tmp_path):
    dataset = tmp_path / "invalid.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "invalid",
                "query": "问题",
                "answerable": True,
                "expected_sources": [],
                "relevant_contains": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="needs sources and relevant text"):
        load_rows(dataset)


def test_load_knowledge_indexes_supported_files_only(tmp_path):
    (tmp_path / "a.txt").write_text("知识 A", encoding="utf-8")
    (tmp_path / "b.md").write_text("知识 B", encoding="utf-8")
    (tmp_path / "ignored.json").write_text("{}", encoding="utf-8")

    result = load_knowledge(IngestionStub(), tmp_path)

    assert result == {"file_count": 2, "chunk_count": 2, "backend": "memory"}

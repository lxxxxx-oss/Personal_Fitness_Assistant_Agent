import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.types import ToolResult
from scripts.eval_rag import (
    build_ragas_metrics,
    collect_samples,
    evaluate_with_ragas,
    generate_with_project_rag,
    load_knowledge,
    load_rows,
)


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


class StubMetric:
    def __init__(self, value):
        self.value = value
        self.calls = []

    async def ascore(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(value=self.value)


def test_rag_eval_dataset_has_reference_and_no_answer_cases():
    rows = load_rows(DATASET_PATH)

    assert len(rows) == 15
    assert all(row["reference"].strip() for row in rows)
    assert sum(row["answerable"] for row in rows) == 12
    assert sum(not row["answerable"] for row in rows) == 3


def test_collect_samples_runs_retrieval_and_generation_for_answerable_only():
    rows = [
        {
            "id": "answerable",
            "category": "test",
            "query": "问题",
            "reference": "参考答案",
            "answerable": True,
        },
        {
            "id": "no_answer",
            "category": "test",
            "query": "知识库外问题",
            "reference": "应拒答",
            "answerable": False,
        },
    ]
    retrieved = [{"source": "gold.txt", "content": "证据", "score": 0.9}]
    calls = []

    def generator(query, contexts):
        calls.append((query, contexts))
        return "生成答案"

    result = collect_samples(
        rows,
        StubRetriever({"问题": retrieved}),
        top_k=3,
        threshold=0.5,
        answer_generator=generator,
    )

    assert result["skipped_unanswerable"] == 1
    assert result["retrieval_mode_counts"] == {"embedding": 1}
    assert calls == [("问题", retrieved)]
    assert result["samples"][0]["retrieved_contexts"] == ["证据"]
    assert result["samples"][0]["response"] == "生成答案"


def test_evaluate_with_ragas_uses_the_three_expected_inputs():
    sample = {
        "id": "case",
        "category": "test",
        "user_input": "问题",
        "reference": "参考答案",
        "response": "生成答案",
        "retrieved_contexts": ["证据"],
        "sources": ["gold.txt"],
        "latency_ms": 1.0,
    }
    metrics = {
        "context_relevance": StubMetric(0.8),
        "faithfulness": StubMetric(0.7),
        "answer_relevance": StubMetric(0.9),
    }

    result = asyncio.run(evaluate_with_ragas([sample], metrics))

    assert result["metrics"] == {
        "context_relevance": 0.8,
        "faithfulness": 0.7,
        "answer_relevance": 0.9,
    }
    assert metrics["context_relevance"].calls == [
        {
            "user_input": "问题",
            "retrieved_contexts": ["证据"],
        }
    ]
    assert metrics["faithfulness"].calls[0]["response"] == "生成答案"
    assert metrics["answer_relevance"].calls == [
        {"user_input": "问题", "response": "生成答案"}
    ]


def test_generate_with_project_rag_uses_chat_generation_node(monkeypatch):
    captured = {}

    def fake_generate_node(state):
        captured.update(state)
        state["result"] = "真实链路答案"
        return state

    monkeypatch.setattr("scripts.eval_rag.generate_node", fake_generate_node)

    response = generate_with_project_rag(
        "问题", [{"source": "a.txt", "content": "证据"}]
    )

    assert response == "真实链路答案"
    assert captured["_retrieved"][0]["content"] == "证据"
    assert captured["memory"] == []


def test_load_rows_rejects_case_without_reference(tmp_path):
    dataset = tmp_path / "invalid.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "invalid",
                "query": "问题",
                "answerable": True,
                "expected_sources": ["gold.txt"],
                "relevant_contains": ["事实"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-empty reference"):
        load_rows(dataset)


def test_load_knowledge_indexes_supported_files_only(tmp_path):
    (tmp_path / "a.txt").write_text("知识 A", encoding="utf-8")
    (tmp_path / "b.md").write_text("知识 B", encoding="utf-8")
    (tmp_path / "ignored.json").write_text("{}", encoding="utf-8")

    result = load_knowledge(IngestionStub(), tmp_path)

    assert result == {"file_count": 2, "chunk_count": 2, "backend": "memory"}


def test_build_ragas_metrics_rejects_unknown_embedding_provider():
    with pytest.raises(ValueError, match="embedding provider"):
        build_ragas_metrics(
            api_key="local-only",
            judge_model="local-judge",
            embedding_model="local-embedding",
            embedding_provider="unknown",
            base_url="http://127.0.0.1:8081/v1",
        )

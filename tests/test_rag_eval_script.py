import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.types import ToolResult
from scripts.eval_rag import (
    build_retriever,
    build_ragas_metrics,
    collect_samples,
    evaluate_with_ragas,
    generate_with_project_rag,
    knowledge_sha256,
    load_knowledge,
    load_progress,
    load_rows,
    save_progress,
    validate_progress_config,
)
from app.tools.retriever import MemoryRetriever, MilvusRetriever


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


def test_build_retriever_selects_explicit_backend_without_fallback(monkeypatch):
    monkeypatch.setattr("scripts.eval_rag.config.milvus_uri", "http://milvus:19530")
    monkeypatch.setattr("scripts.eval_rag.config.milvus_collection_name", "rag_eval")

    memory = build_retriever("memory", "mock-embedding")
    milvus = build_retriever("milvus", "mock-embedding")

    assert isinstance(memory, MemoryRetriever)
    assert isinstance(milvus, MilvusRetriever)
    assert milvus.uri == "http://milvus:19530"
    assert milvus.collection_name == "rag_eval"
    assert not hasattr(milvus, "fallback")


def test_build_retriever_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unsupported retriever backend"):
        build_retriever("unknown", "mock-embedding")


def test_rag_eval_dataset_has_reference_and_no_answer_cases():
    rows = load_rows(DATASET_PATH)

    assert len(rows) == 21
    assert all(row["reference"].strip() for row in rows)
    assert sum(row["answerable"] for row in rows) == 19
    assert sum(not row["answerable"] for row in rows) == 2


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


def test_collect_samples_resumes_and_checkpoints_only_new_cases():
    rows = [
        {
            "id": case_id,
            "category": "test",
            "query": f"问题-{case_id}",
            "reference": "参考答案",
            "answerable": True,
        }
        for case_id in ("done", "new-1", "new-2")
    ]
    existing = {
        "id": "done",
        "category": "test",
        "user_input": "问题-done",
        "reference": "参考答案",
        "response": "已有答案",
        "retrieved_contexts": ["已有证据"],
        "sources": ["old.txt"],
        "retrieval_mode": "embedding",
        "latency_ms": 1.0,
    }
    checkpoints = []

    result = collect_samples(
        rows,
        StubRetriever(
            {
                "问题-new-1": [
                    {"source": "new.txt", "content": "新证据", "score": 0.9}
                ]
            }
        ),
        top_k=3,
        threshold=0.5,
        answer_generator=lambda query, contexts: f"回答-{query}",
        existing_samples=[existing],
        max_new_cases=1,
        on_sample=lambda samples, modes: checkpoints.append((samples, modes)),
    )

    assert [sample["id"] for sample in result["samples"]] == ["done", "new-1"]
    assert result["new_cases"] == 1
    assert result["retrieval_mode_counts"] == {"embedding": 2}
    assert len(checkpoints) == 1
    assert [sample["id"] for sample in checkpoints[0][0]] == ["done", "new-1"]


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


def test_evaluate_with_ragas_resumes_scored_case_and_checkpoints_new_case():
    samples = [
        {
            "id": case_id,
            "category": "test",
            "user_input": f"问题-{case_id}",
            "reference": "参考答案",
            "response": "生成答案",
            "retrieved_contexts": ["证据"],
            "sources": ["gold.txt"],
            "latency_ms": 1.0,
        }
        for case_id in ("done", "new")
    ]
    existing = {
        **samples[0],
        "scores": {
            "context_relevance": 0.6,
            "faithfulness": 0.7,
            "answer_relevance": 0.8,
        },
    }
    metrics = {
        "context_relevance": StubMetric(0.9),
        "faithfulness": StubMetric(0.9),
        "answer_relevance": StubMetric(0.9),
    }
    checkpoints = []

    result = asyncio.run(
        evaluate_with_ragas(
            samples,
            metrics,
            existing_cases=[existing],
            on_case=lambda cases: checkpoints.append(cases),
        )
    )

    assert len(metrics["context_relevance"].calls) == 1
    assert metrics["context_relevance"].calls[0]["user_input"] == "问题-new"
    assert len(checkpoints) == 1
    assert [case["id"] for case in result["cases"]] == ["done", "new"]
    assert result["metrics"]["context_relevance"] == pytest.approx(0.75)


def test_progress_round_trip_and_config_guard(tmp_path):
    path = tmp_path / "nested" / "progress.json"
    payload = {
        "schema_version": 1,
        "config": {"dataset_sha256": "abc", "top_k": 3},
        "samples": [{"id": "case"}],
    }

    save_progress(path, payload)

    assert load_progress(path) == payload
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    validate_progress_config(load_progress(path), payload["config"])
    with pytest.raises(ValueError, match="configuration does not match"):
        validate_progress_config(load_progress(path), {"top_k": 5})


def test_knowledge_fingerprint_ignores_absolute_directory(tmp_path):
    first = tmp_path / "pc-a" / "knowledge"
    second = tmp_path / "pc-b" / "knowledge"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    for directory in (first, second):
        (directory / "a.txt").write_text("知识 A", encoding="utf-8")
        (directory / "b.md").write_text("知识 B", encoding="utf-8")

    assert knowledge_sha256(first) == knowledge_sha256(second)
    (second / "b.md").write_text("知识已变化", encoding="utf-8")
    assert knowledge_sha256(first) != knowledge_sha256(second)


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

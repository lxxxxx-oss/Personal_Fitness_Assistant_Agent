import pytest

from app.tools.types import ToolResult
from scripts.eval_retrieval import comparison_delta, evaluate_retrieval, relevant_rank


class StubRetriever:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query

    def search(self, query, top_k, threshold):
        return ToolResult.ok(
            data=self.results_by_query.get(query, [])[:top_k],
            mode="hybrid",
        )


def test_relevant_rank_requires_matching_source_and_evidence_text():
    results = [
        {"source": "wrong.txt", "content": "每周 150-300 分钟"},
        {"source": "who.txt", "content": "建议每周 150 - 300 分钟"},
        {"source": "who.txt", "content": "每周 150-300 分钟中等强度"},
    ]

    assert relevant_rank(results, ["who.txt"], ["150-300分钟中等强度"]) == 3


def test_evaluate_retrieval_calculates_hit_mrr_rejection_and_latency():
    rows = [
        {
            "id": "hit-at-2",
            "query": "q1",
            "answerable": True,
            "expected_sources": ["gold.txt"],
            "relevant_contains": ["正确证据"],
        },
        {
            "id": "miss",
            "query": "q2",
            "answerable": True,
            "expected_sources": ["gold.txt"],
            "relevant_contains": ["正确证据"],
        },
        {
            "id": "reject",
            "query": "q3",
            "answerable": False,
            "expected_sources": [],
            "relevant_contains": [],
        },
    ]
    retriever = StubRetriever(
        {
            "q1": [
                {"source": "noise.txt", "content": "干扰"},
                {"source": "gold.txt", "content": "这里是正确证据"},
            ],
            "q2": [{"source": "noise.txt", "content": "干扰"}],
            "q3": [],
        }
    )

    result = evaluate_retrieval(rows, retriever, top_k=5, threshold=0.5)

    assert result["recall_at_k"] == 0.5
    assert result["mrr"] == 0.25
    assert result["unanswerable_rejection_rate"] == 1.0
    assert result["cases"][0]["relevant_rank"] == 2


def test_comparison_delta_uses_hybrid_minus_dense():
    dense = {"recall_at_k": 0.5, "mrr": 0.4, "latency_ms": {"mean": 10.0}}
    hybrid = {"recall_at_k": 0.75, "mrr": 0.6, "latency_ms": {"mean": 13.5}}

    delta = comparison_delta(dense, hybrid)

    assert delta["recall_at_k"] == pytest.approx(0.25)
    assert delta["mrr"] == pytest.approx(0.2)
    assert delta["mean_latency_ms"] == pytest.approx(3.5)

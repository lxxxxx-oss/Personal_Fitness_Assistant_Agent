"""Memory + Context benchmark script tests."""
from pathlib import Path

from scripts.eval_memory_context import evaluate, load_rows


BENCHMARK_PATH = Path("data/eval/memory_context_benchmark.jsonl")


def test_load_memory_context_benchmark_dataset():
    rows = load_rows(BENCHMARK_PATH)
    categories = {row["category"] for row in rows}

    assert rows
    assert {
        "memory_recall",
        "sensitive_candidate",
        "prompt_memory_injection",
        "compact",
        "rag_source",
        "conversation_summary",
    } <= categories


def test_memory_context_benchmark_is_currently_green():
    rows = load_rows(BENCHMARK_PATH)
    result = evaluate(rows)

    assert result["total"] == len(rows)
    assert result["failed"] == 0
    assert result["pass_rate"] == 1.0
    assert result["by_category"]["memory_recall"]["pass_rate"] == 1.0
    assert result["by_category"]["compact"]["pass_rate"] == 1.0
    assert result["by_category"]["conversation_summary"]["pass_rate"] == 1.0

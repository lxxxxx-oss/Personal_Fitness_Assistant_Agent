"""Memory + Context benchmark script tests."""
from pathlib import Path

import pytest

from scripts.eval_memory_context import _string_list, evaluate, load_rows


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
    assert result["by_category"]["conversation_summary"]["total"] == 6


def test_benchmark_marker_accepts_one_string_or_a_string_list():
    assert _string_list("膝伤") == ["膝伤"]
    assert _string_list(["膝伤", "低冲击"]) == ["膝伤", "低冲击"]
    assert _string_list(None) == []

    with pytest.raises(ValueError, match="string or a list of strings"):
        _string_list(["膝伤", 1])

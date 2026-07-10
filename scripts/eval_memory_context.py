"""Evaluate Memory + Context + RAG benchmark cases."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import config
from app.graph.prompt_builder import PromptBuilder
from app.graph.subgraphs.rag_context import build_rag_context
from app.memory.memory_store import MemoryStore


DEFAULT_DATASET = Path("data/eval/memory_context_benchmark.jsonl")


def load_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc
            if not isinstance(row.get("id"), str) or not row["id"].strip():
                raise ValueError(f"Line {line_no} must include non-empty id")
            if row.get("category") not in {
                "memory_recall",
                "sensitive_candidate",
                "prompt_memory_injection",
                "compact",
                "rag_source",
            }:
                raise ValueError(f"Line {line_no} has invalid category")
            rows.append(row)
    return rows


def evaluate(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    cases = []
    total = 0
    passed = 0
    category_total = Counter()
    category_passed = Counter()

    for row in rows:
        result = evaluate_case(row)
        total += 1
        passed += int(result["passed"])
        category = row["category"]
        category_total[category] += 1
        category_passed[category] += int(result["passed"])
        cases.append(result)

    by_category = {
        category: {
            "total": category_total[category],
            "passed": category_passed[category],
            "pass_rate": (
                category_passed[category] / category_total[category]
                if category_total[category]
                else 0.0
            ),
        }
        for category in sorted(category_total)
    }
    failures = [case for case in cases if not case["passed"]]
    return {
        "total": total,
        "passed": passed,
        "failed": len(failures),
        "pass_rate": passed / total if total else 0.0,
        "by_category": by_category,
        "failures": failures,
        "cases": cases,
    }


def evaluate_case(row: Dict[str, Any]) -> Dict[str, Any]:
    category = row["category"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        store = MemoryStore(str(Path(tmpdir) / "memory.db"))
        if category == "memory_recall":
            return _eval_memory_recall(row, store)
        if category == "sensitive_candidate":
            return _eval_sensitive_candidate(row, store)
        if category == "prompt_memory_injection":
            return _eval_prompt_memory_injection(row)
        if category == "compact":
            return _eval_compact(row)
        if category == "rag_source":
            return _eval_rag_source(row)
    raise ValueError(f"Unsupported category: {category}")


def _base_result(row: Dict[str, Any], passed: bool, details: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "category": row["category"],
        "passed": passed,
        "details": details,
    }


def _eval_memory_recall(row: Dict[str, Any], store: MemoryStore) -> Dict[str, Any]:
    user_id = row.get("user_id", "benchmark_user")
    for item in row.get("setup_memories", []):
        store.create_memory(
            user_id=user_id,
            kind=item.get("kind", "note"),
            content=item["content"],
            source_type=item.get("source_type", "manual_import"),
            importance=float(item.get("importance", 0.5)),
        )
    results = store.search_memories(user_id, row["query"], limit=int(row.get("top_k", 5)))
    expected = row["expected_memory_contains"]
    passed = any(expected in item["content"] for item in results)
    return _base_result(
        row,
        passed,
        {
            "expected": expected,
            "retrieved": [item["content"] for item in results],
            "scores": [item.get("score") for item in results],
        },
    )


def _eval_sensitive_candidate(row: Dict[str, Any], store: MemoryStore) -> Dict[str, Any]:
    user_id = row.get("user_id", "benchmark_user")
    result = store.remember_explicit(user_id, row["message"])
    pending = store.list_candidate_memories(user_id)
    memories = store.list_memories(user_id)
    passed = (
        bool(result)
        and bool(result.get("candidate")) == bool(row.get("expected_candidate", True))
        and result.get("privacy_level") == row.get("expected_privacy_level")
        and len(pending) == 1
        and len(memories) == 0
    )
    return _base_result(
        row,
        passed,
        {
            "candidate": result,
            "pending_count": len(pending),
            "active_memory_count": len(memories),
        },
    )


def _eval_prompt_memory_injection(row: Dict[str, Any]) -> Dict[str, Any]:
    state = {
        "user_input": row["user_input"],
        "memory": [],
        "_long_term_memories": row.get("long_term_memories", []),
    }
    prompt = PromptBuilder.chat_answer(state, context_text="", sources=[])
    expected = row["expected_prompt_contains"]
    return _base_result(
        row,
        expected in prompt,
        {
            "expected": expected,
            "prompt_chars": len(prompt),
            "prompt_meta": state.get("_prompt_meta", {}),
        },
    )


def _eval_compact(row: Dict[str, Any]) -> Dict[str, Any]:
    original_trigger = config.context_compact_trigger_chars
    original_max = config.context_max_prompt_chars
    try:
        config.context_compact_trigger_chars = int(row["compact_trigger_chars"])
        config.context_max_prompt_chars = int(row["max_prompt_chars"])
        state = {
            "user_input": row["user_input"],
            "memory": [
                {"role": "user", "content": "旧对话" * int(row["memory_repeat"])},
                {"role": "assistant", "content": "旧回答" * int(row["memory_repeat"])},
            ],
            "_structured_state": {"task": {"primary_intent": "chat"}},
        }
        prompt = PromptBuilder.chat_answer(
            state,
            context_text="保持核心稳定。" * int(row["context_repeat"]),
            sources=[],
        )
        prompt_meta = state.get("_prompt_meta", {})
        passed = (
            bool(prompt_meta.get("compact_triggered")) == bool(row["expected_compact"])
            and len(prompt) <= int(row["max_prompt_chars"])
            and "compact_summary" in state.get("_structured_state", {})
        )
        return _base_result(
            row,
            passed,
            {
                "prompt_chars": len(prompt),
                "prompt_meta": prompt_meta,
                "execution": state.get("_execution", []),
            },
        )
    finally:
        config.context_compact_trigger_chars = original_trigger
        config.context_max_prompt_chars = original_max


def _eval_rag_source(row: Dict[str, Any]) -> Dict[str, Any]:
    context, sources = build_rag_context(row.get("retrieved", []))
    expected_sources = row.get("expected_sources", [])
    expected_refs = row.get("expected_refs", [])
    passed = sources == expected_sources and all(ref in context for ref in expected_refs)
    return _base_result(
        row,
        passed,
        {
            "sources": sources,
            "expected_sources": expected_sources,
            "context": context,
        },
    )


def print_report(result: Dict[str, Any], *, include_cases: bool = False) -> None:
    print(
        f"Memory/Context benchmark: {result['passed']}/{result['total']} passed "
        f"({result['pass_rate']:.2%})"
    )
    for category, stats in result["by_category"].items():
        print(
            f"- {category}: {stats['passed']}/{stats['total']} "
            f"({stats['pass_rate']:.2%})"
        )
    if result["failures"]:
        print("\nFailures:")
        for case in result["failures"]:
            print(f"- {case['id']}: {json.dumps(case['details'], ensure_ascii=False)}")
    if include_cases:
        print("\nCases:")
        for case in result["cases"]:
            status = "PASS" if case["passed"] else "FAIL"
            print(f"- [{status}] {case['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    parser.add_argument("--include-cases", action="store_true")
    parser.add_argument("--fail-on-fail", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.dataset)
    result = evaluate(rows)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result, include_cases=args.include_cases)
    if args.fail_on_fail and result["failed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

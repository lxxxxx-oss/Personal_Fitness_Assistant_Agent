"""Evaluate RAG retrieval quality on a JSONL golden set."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import config
from app.tools.retriever import MemoryRetriever


DEFAULT_DATASET = Path("data/eval/rag_eval.jsonl")
DEFAULT_KNOWLEDGE_DIR = Path("data/knowledge")


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """Load and validate retrieval cases from a JSONL file."""
    rows: List[Dict[str, Any]] = []
    seen_ids = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc

            case_id = row.get("id")
            query = row.get("query")
            answerable = row.get("answerable")
            expected_sources = row.get("expected_sources", [])
            relevant_contains = row.get("relevant_contains", [])
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError(f"Line {line_no} must include non-empty id")
            if case_id in seen_ids:
                raise ValueError(f"Line {line_no} has duplicate id {case_id!r}")
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"Line {line_no} must include non-empty query")
            if not isinstance(answerable, bool):
                raise ValueError(f"Line {line_no} must include boolean answerable")
            if not _is_string_list(expected_sources):
                raise ValueError(f"Line {line_no} expected_sources must be string list")
            if not _is_string_list(relevant_contains):
                raise ValueError(f"Line {line_no} relevant_contains must be string list")
            if answerable and (not expected_sources or not relevant_contains):
                raise ValueError(
                    f"Line {line_no} answerable case needs sources and relevant text"
                )
            if not answerable and (expected_sources or relevant_contains):
                raise ValueError(
                    f"Line {line_no} unanswerable case must not define gold evidence"
                )
            seen_ids.add(case_id)
            rows.append(row)
    if not rows:
        raise ValueError("RAG evaluation dataset is empty")
    return rows


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def load_knowledge(retriever: Any, knowledge_dir: Path) -> Dict[str, Any]:
    """Index UTF-8 text/Markdown files and return ingestion accounting."""
    if not knowledge_dir.is_dir():
        raise ValueError(f"Knowledge directory not found: {knowledge_dir}")
    files = sorted(
        path for path in knowledge_dir.iterdir() if path.suffix.lower() in {".txt", ".md"}
    )
    if not files:
        raise ValueError(f"No .txt or .md knowledge files in: {knowledge_dir}")
    documents = [path.read_text(encoding="utf-8") for path in files]
    result = retriever.add_documents(documents, sources=[path.name for path in files])
    if not result.ok:
        raise RuntimeError(
            f"Knowledge ingestion failed: {result.error_code} {result.error_message}"
        )
    return {
        "file_count": len(files),
        "chunk_count": int(result.data.get("upserted", 0)),
        "backend": result.meta.get("backend", "unknown"),
    }


def evaluate(
    rows: Iterable[Dict[str, Any]],
    retriever: Any,
    *,
    top_k: int,
    threshold: float,
) -> Dict[str, Any]:
    """Calculate retrieval, source, rejection and latency metrics."""
    cases = []
    answerable_total = 0
    relevant_hits = 0
    source_hits = 0
    reciprocal_rank_sum = 0.0
    unanswerable_total = 0
    rejected = 0
    latencies_ms: List[float] = []
    mode_counts: Counter[str] = Counter()

    for row in rows:
        started = time.perf_counter()
        result = retriever.search(row["query"], top_k=top_k, threshold=threshold)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies_ms.append(latency_ms)
        if not result.ok:
            raise RuntimeError(
                f"Search failed for {row['id']}: "
                f"{result.error_code} {result.error_message}"
            )
        retrieved = list(result.data or [])
        mode = str(result.meta.get("mode", "unknown"))
        mode_counts[mode] += 1
        rank = _first_relevant_rank(row, retrieved)
        source_hit = _has_expected_source(row, retrieved)

        if row["answerable"]:
            answerable_total += 1
            relevant_hits += int(rank is not None)
            source_hits += int(source_hit)
            if rank is not None:
                reciprocal_rank_sum += 1.0 / rank
            passed = rank is not None
        else:
            unanswerable_total += 1
            was_rejected = len(retrieved) == 0
            rejected += int(was_rejected)
            passed = was_rejected

        cases.append(
            {
                "id": row["id"],
                "category": row.get("category", "uncategorized"),
                "query": row["query"],
                "answerable": row["answerable"],
                "passed": passed,
                "first_relevant_rank": rank,
                "source_hit": source_hit,
                "mode": mode,
                "latency_ms": latency_ms,
                "retrieved": [
                    {
                        "source": item.get("source", ""),
                        "score": float(item.get("score", 0.0)),
                        "content": str(item.get("content", "")),
                    }
                    for item in retrieved
                ],
            }
        )

    recall_at_k = relevant_hits / answerable_total if answerable_total else 0.0
    mrr = reciprocal_rank_sum / answerable_total if answerable_total else 0.0
    source_hit_rate = source_hits / answerable_total if answerable_total else 0.0
    no_answer_rejection_rate = (
        rejected / unanswerable_total if unanswerable_total else 0.0
    )
    return {
        "total": len(cases),
        "answerable_total": answerable_total,
        "unanswerable_total": unanswerable_total,
        "top_k": top_k,
        "threshold": threshold,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "source_hit_rate": source_hit_rate,
        "no_answer_rejection_rate": no_answer_rejection_rate,
        "average_latency_ms": _mean(latencies_ms),
        "p95_latency_ms": _percentile(latencies_ms, 0.95),
        "mode_counts": dict(mode_counts),
        "failures": [case for case in cases if not case["passed"]],
        "cases": cases,
    }


def _first_relevant_rank(
    row: Dict[str, Any], retrieved: Sequence[Dict[str, Any]]
) -> int | None:
    if not row["answerable"]:
        return None
    expected_sources = set(row["expected_sources"])
    expected_text = row["relevant_contains"]
    for rank, item in enumerate(retrieved, start=1):
        content = str(item.get("content", ""))
        if item.get("source") in expected_sources and any(
            phrase in content for phrase in expected_text
        ):
            return rank
    return None


def _has_expected_source(
    row: Dict[str, Any], retrieved: Sequence[Dict[str, Any]]
) -> bool:
    expected_sources = set(row.get("expected_sources", []))
    return bool(expected_sources) and any(
        item.get("source") in expected_sources for item in retrieved
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return ordered[index]


def print_report(result: Dict[str, Any], *, show_cases: bool = False) -> None:
    print("RAG Retrieval Eval")
    print("=" * 72)
    print(
        f"Cases: {result['total']} | answerable: {result['answerable_total']} | "
        f"unanswerable: {result['unanswerable_total']}"
    )
    print(
        f"Recall@{result['top_k']}: {result['recall_at_k']:.1%} | "
        f"MRR: {result['mrr']:.3f} | "
        f"source hit: {result['source_hit_rate']:.1%} | "
        f"no-answer rejection: {result['no_answer_rejection_rate']:.1%}"
    )
    print(
        f"Latency avg/p95: {result['average_latency_ms']:.2f}/"
        f"{result['p95_latency_ms']:.2f} ms | modes: {result['mode_counts']}"
    )
    if result["failures"]:
        print("\nFailures")
        print("-" * 72)
        for case in result["failures"]:
            print(
                f"{case['id']}: answerable={case['answerable']} "
                f"rank={case['first_relevant_rank']} query={case['query']}"
            )
    if show_cases:
        print("\nAll cases")
        print("-" * 72)
        for case in result["cases"]:
            status = "OK" if case["passed"] else "FAIL"
            hits = ", ".join(
                f"{item['source']}:{item['score']:.3f}" for item in case["retrieved"]
            ) or "empty"
            print(f"{status:<4} {case['id']:<24} rank={case['first_relevant_rank']} {hits}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--top-k", type=int, default=config.retriever_top_k)
    parser.add_argument("--threshold", type=float, default=config.retriever_threshold)
    parser.add_argument("--embedding-model", default=config.embedding_model)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show-cases", action="store_true")
    parser.add_argument(
        "--require-embedding",
        action="store_true",
        help="Fail when the embedding model is unavailable and keyword fallback is used.",
    )
    parser.add_argument("--min-recall", type=float)
    parser.add_argument("--min-mrr", type=float)
    parser.add_argument("--min-no-answer-rejection", type=float)
    args = parser.parse_args()

    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")
    for name in ("min_recall", "min_mrr", "min_no_answer_rejection"):
        value = getattr(args, name)
        if value is not None and not 0.0 <= value <= 1.0:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1")

    retriever = MemoryRetriever(embedding_model=args.embedding_model)
    ingestion = load_knowledge(retriever, args.knowledge_dir)
    result = evaluate(
        load_rows(args.dataset),
        retriever,
        top_k=args.top_k,
        threshold=args.threshold,
    )
    result["ingestion"] = ingestion
    result["embedding_model"] = args.embedding_model
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result, show_cases=args.show_cases)

    failed = False
    if args.require_embedding and set(result["mode_counts"]) != {"embedding"}:
        failed = True
    if args.min_recall is not None and result["recall_at_k"] < args.min_recall:
        failed = True
    if args.min_mrr is not None and result["mrr"] < args.min_mrr:
        failed = True
    if (
        args.min_no_answer_rejection is not None
        and result["no_answer_rejection_rate"] < args.min_no_answer_rejection
    ):
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare dense and hybrid retrieval without calling a generator or RAGAS."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.eval_rag import (
    DEFAULT_DATASET,
    DEFAULT_KNOWLEDGE_DIR,
    build_retriever,
    load_knowledge,
    load_rows,
)

from app.config import config


def _normalized(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def relevant_rank(
    results: Sequence[Mapping[str, Any]],
    expected_sources: Sequence[str],
    relevant_contains: Sequence[str],
) -> int | None:
    """Return the 1-based rank of the first result matching source and gold text."""
    expected = {_normalized(source) for source in expected_sources}
    evidence = [_normalized(fragment) for fragment in relevant_contains]
    for rank, result in enumerate(results, start=1):
        if _normalized(result.get("source")) not in expected:
            continue
        content = _normalized(result.get("content"))
        if any(fragment in content for fragment in evidence):
            return rank
    return None


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile + 0.999) - 1))
    return ordered[index]


def evaluate_retrieval(
    rows: Iterable[Mapping[str, Any]],
    retriever: Any,
    *,
    top_k: int,
    threshold: float,
) -> Dict[str, Any]:
    """Measure hit-style Recall@K, MRR, refusal rate, and retrieval latency."""
    cases: List[Dict[str, Any]] = []
    latencies: List[float] = []
    answerable_count = 0
    hits = 0
    reciprocal_rank_sum = 0.0
    unanswerable_count = 0
    empty_unanswerable = 0

    for row in rows:
        started = time.perf_counter()
        result = retriever.search(str(row["query"]), top_k, threshold)
        latency_ms = (time.perf_counter() - started) * 1000
        if not result.ok:
            raise RuntimeError(
                f"Retrieval failed for {row['id']}: "
                f"{result.error_code} {result.error_message}"
            )
        retrieved = list(result.data or [])
        rank = None
        if bool(row["answerable"]):
            answerable_count += 1
            rank = relevant_rank(
                retrieved,
                row.get("expected_sources", []),
                row.get("relevant_contains", []),
            )
            if rank is not None:
                hits += 1
                reciprocal_rank_sum += 1.0 / rank
        else:
            unanswerable_count += 1
            empty_unanswerable += int(not retrieved)
        latencies.append(latency_ms)
        cases.append(
            {
                "id": row["id"],
                "answerable": bool(row["answerable"]),
                "relevant_rank": rank,
                "result_count": len(retrieved),
                "mode": result.meta.get("mode", "unknown"),
                "latency_ms": round(latency_ms, 3),
                "sources": [item.get("source") for item in retrieved],
            }
        )

    if answerable_count == 0:
        raise ValueError("Retrieval evaluation needs at least one answerable case")
    return {
        "case_count": len(cases),
        "answerable_count": answerable_count,
        "recall_at_k": hits / answerable_count,
        "mrr": reciprocal_rank_sum / answerable_count,
        "unanswerable_rejection_rate": (
            empty_unanswerable / unanswerable_count if unanswerable_count else None
        ),
        "latency_ms": {
            "mean": statistics.fmean(latencies),
            "p50": statistics.median(latencies),
            "p95": _percentile(latencies, 0.95),
        },
        "cases": cases,
    }


def comparison_delta(dense: Mapping[str, Any], hybrid: Mapping[str, Any]) -> Dict[str, float]:
    """Return hybrid-minus-dense deltas; negative latency means faster."""
    return {
        "recall_at_k": float(hybrid["recall_at_k"]) - float(dense["recall_at_k"]),
        "mrr": float(hybrid["mrr"]) - float(dense["mrr"]),
        "mean_latency_ms": (
            float(hybrid["latency_ms"]["mean"])
            - float(dense["latency_ms"]["mean"])
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--strategy", choices=("dense", "hybrid", "both"), default="both")
    parser.add_argument(
        "--retriever-backend",
        choices=("memory", "sqlite_faiss"),
        default=config.retriever_backend,
    )
    parser.add_argument(
        "--retriever-db-path",
        type=Path,
        default=Path(config.retriever_db_path),
    )
    parser.add_argument("--embedding-model", default=config.embedding_model)
    parser.add_argument("--top-k", type=int, default=config.retriever_top_k)
    parser.add_argument(
        "--threshold",
        type=float,
        default=config.retriever_threshold,
        help=(
            "Minimum cosine score for the dense-only baseline; hybrid retrieval "
            "does not pre-filter Dense candidates before RRF"
        ),
    )
    parser.add_argument("--candidate-k", type=int, default=config.retriever_candidate_k)
    parser.add_argument("--rrf-k", type=int, default=config.retriever_rrf_k)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--show-cases", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    if not 1 <= args.candidate_k <= 100:
        parser.error("--candidate-k must be between 1 and 100")
    if args.rrf_k < 1:
        parser.error("--rrf-k must be positive")
    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")

    rows = load_rows(args.dataset)
    strategies = ("dense", "hybrid") if args.strategy == "both" else (args.strategy,)
    report: Dict[str, Any] = {
        "config": {
            "backend": args.retriever_backend,
            "top_k": args.top_k,
            "threshold": args.threshold,
            "threshold_scope": "dense_only",
            "hybrid_dense_threshold_applied": False,
            "candidate_k": args.candidate_k,
            "rrf_k": args.rrf_k,
        },
        "strategies": {},
    }
    for strategy in strategies:
        retriever = build_retriever(
            args.retriever_backend,
            args.embedding_model,
            strategy=strategy,
            candidate_k=args.candidate_k,
            rrf_k=args.rrf_k,
            db_path=args.retriever_db_path,
        )
        try:
            ingestion = load_knowledge(retriever, args.knowledge_dir)
            measured = evaluate_retrieval(
                rows,
                retriever,
                top_k=args.top_k,
                threshold=args.threshold,
            )
            if not args.show_cases:
                measured.pop("cases", None)
            report["strategies"][strategy] = {"ingestion": ingestion, **measured}
        finally:
            if hasattr(retriever, "close"):
                retriever.close()
    if set(strategies) == {"dense", "hybrid"}:
        report["hybrid_minus_dense"] = comparison_delta(
            report["strategies"]["dense"],
            report["strategies"]["hybrid"],
        )

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

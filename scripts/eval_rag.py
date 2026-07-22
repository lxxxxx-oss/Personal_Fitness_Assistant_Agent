"""Evaluate the project's real RAG chain with three RAGAS metrics."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Protocol, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import config
from app.graph.subgraphs.chat import generate_node
from app.tools.retriever import MemoryRetriever, MilvusRetriever


DEFAULT_DATASET = Path("data/eval/rag_eval.jsonl")
DEFAULT_KNOWLEDGE_DIR = Path("data/knowledge")
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
DEFAULT_JUDGE_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_JUDGE_EMBEDDING_PROVIDER = "openai"
DEFAULT_PROGRESS_FILE = Path("tmp/rag_eval_progress.json")
PROGRESS_SCHEMA_VERSION = 1
METRIC_LABELS = {
    "context_relevance": "上下文相关性",
    "faithfulness": "忠实度",
    "answer_relevance": "答案相关性",
}


class RagasMetric(Protocol):
    """Small seam around RAGAS scorers so data flow can be unit-tested."""

    async def ascore(self, **kwargs: Any) -> Any: ...


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """Load and validate RAG cases from JSONL."""
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
            reference = row.get("reference")
            answerable = row.get("answerable")
            expected_sources = row.get("expected_sources", [])
            relevant_contains = row.get("relevant_contains", [])
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError(f"Line {line_no} must include non-empty id")
            if case_id in seen_ids:
                raise ValueError(f"Line {line_no} has duplicate id {case_id!r}")
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f"Line {line_no} must include non-empty query")
            if not isinstance(reference, str) or not reference.strip():
                raise ValueError(f"Line {line_no} must include non-empty reference")
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


def file_sha256(path: Path) -> str:
    """Return a stable dataset fingerprint without exposing file contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def knowledge_sha256(knowledge_dir: Path) -> str:
    """Fingerprint the indexed text corpus independently of its absolute path."""
    files = sorted(
        path for path in knowledge_dir.iterdir() if path.suffix.lower() in {".txt", ".md"}
    )
    if not files:
        raise ValueError(f"No .txt or .md knowledge files in: {knowledge_dir}")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def load_progress(path: Path) -> Dict[str, Any]:
    """Load and minimally validate a resumable evaluation artifact."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid progress JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Progress file must contain a JSON object: {path}")
    if payload.get("schema_version") != PROGRESS_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported progress schema in {path}: "
            f"{payload.get('schema_version')!r}"
        )
    if not isinstance(payload.get("samples"), list):
        raise ValueError(f"Progress file has no samples list: {path}")
    return payload


def save_progress(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically persist progress so an interruption cannot leave partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def validate_progress_config(
    progress: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    """Reject stale checkpoints instead of silently mixing unlike evaluations."""
    actual = progress.get("config")
    if actual != dict(expected):
        raise ValueError(
            "Progress configuration does not match this run; use --fresh or a "
            "different --progress-file"
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


def build_retriever(backend: str, embedding_model: str) -> Any:
    """Build the requested evaluation backend without implicit fallback."""
    if backend == "memory":
        return MemoryRetriever(embedding_model=embedding_model)
    if backend == "milvus":
        return MilvusRetriever(
            uri=config.milvus_uri,
            collection_name=config.milvus_collection_name,
            token=config.milvus_token,
            embedding_model=embedding_model,
            index_type=config.milvus_index_type,
            nlist=config.milvus_nlist,
            nprobe=config.milvus_nprobe,
            timeout_seconds=config.milvus_timeout_seconds,
        )
    raise ValueError(f"Unsupported retriever backend: {backend}")


def collect_samples(
    rows: Iterable[Dict[str, Any]],
    retriever: Any,
    *,
    top_k: int,
    threshold: float,
    answer_generator: Any,
    existing_samples: Sequence[Dict[str, Any]] = (),
    max_new_cases: int | None = None,
    on_sample: Callable[[List[Dict[str, Any]], Dict[str, int]], None] | None = None,
) -> Dict[str, Any]:
    """Generate answerable samples, optionally resuming and checkpointing per case."""
    samples: List[Dict[str, Any]] = [dict(sample) for sample in existing_samples]
    completed_ids = {str(sample.get("id", "")) for sample in samples}
    if len(completed_ids) != len(samples) or "" in completed_ids:
        raise ValueError("Existing samples must have unique non-empty ids")
    skipped_unanswerable = 0
    mode_counts: Counter[str] = Counter(
        str(sample.get("retrieval_mode", "unknown")) for sample in samples
    )
    new_cases = 0

    for row in rows:
        if not row["answerable"]:
            skipped_unanswerable += 1
            continue
        if row["id"] in completed_ids:
            continue
        if max_new_cases is not None and new_cases >= max_new_cases:
            continue
        started = time.perf_counter()
        result = retriever.search(row["query"], top_k=top_k, threshold=threshold)
        if not result.ok:
            raise RuntimeError(
                f"Search failed for {row['id']}: "
                f"{result.error_code} {result.error_message}"
            )
        retrieved = list(result.data or [])
        retrieval_mode = str(result.meta.get("mode", "unknown"))
        mode_counts[retrieval_mode] += 1
        response = answer_generator(row["query"], retrieved)
        if not isinstance(response, str) or not response.strip():
            raise RuntimeError(f"Generation returned an empty response for {row['id']}")
        samples.append(
            {
                "id": row["id"],
                "category": row.get("category", "uncategorized"),
                "user_input": row["query"],
                "reference": row["reference"],
                "response": response.strip(),
                "retrieved_contexts": [
                    str(item.get("content", "")).strip()
                    for item in retrieved
                    if str(item.get("content", "")).strip()
                ],
                "sources": [
                    str(item.get("source", "")).strip()
                    for item in retrieved
                    if str(item.get("source", "")).strip()
                ],
                "retrieval_mode": retrieval_mode,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
        completed_ids.add(row["id"])
        new_cases += 1
        if on_sample is not None:
            on_sample(samples, dict(mode_counts))
    if not samples:
        raise ValueError("RAGAS needs at least one answerable evaluation case")
    return {
        "samples": samples,
        "skipped_unanswerable": skipped_unanswerable,
        "retrieval_mode_counts": dict(mode_counts),
        "new_cases": new_cases,
    }


def generate_with_project_rag(query: str, retrieved: Sequence[Dict[str, Any]]) -> str:
    """Generate through the production chat RAG node, without routing side effects."""
    state: Dict[str, Any] = {
        "user_input": query,
        "memory": [],
        "_long_term_memories": [],
        "_conversation_summary": "",
        "_retrieved": list(retrieved),
    }
    return str(generate_node(state).get("result", ""))


def build_ragas_metrics(
    *,
    api_key: str,
    judge_model: str,
    embedding_model: str,
    embedding_provider: str = DEFAULT_JUDGE_EMBEDDING_PROVIDER,
    base_url: str | None = None,
) -> Dict[str, RagasMetric]:
    """Build three RAGAS scorers; credentials remain input-only and are never returned."""
    if not api_key.strip():
        raise ValueError("OPENAI_API_KEY is required for the RAGAS judge")
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings import HuggingFaceEmbeddings
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextRelevance,
            Faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError(
            "RAGAS dependencies are missing; install requirements-eval.txt"
        ) from exc

    client_kwargs: Dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = AsyncOpenAI(**client_kwargs)
    judge_llm = llm_factory(judge_model, client=client)
    if embedding_provider == "openai":
        judge_embeddings = embedding_factory(
            "openai", model=embedding_model, client=client
        )
    elif embedding_provider == "huggingface":
        judge_embeddings = HuggingFaceEmbeddings(model=embedding_model)
    else:
        raise ValueError(
            "judge embedding provider must be 'openai' or 'huggingface'"
        )
    return {
        "context_relevance": ContextRelevance(llm=judge_llm),
        "faithfulness": Faithfulness(llm=judge_llm),
        "answer_relevance": AnswerRelevancy(
            llm=judge_llm,
            embeddings=judge_embeddings,
        ),
    }


async def evaluate_with_ragas(
    samples: Sequence[Dict[str, Any]],
    metrics: Mapping[str, RagasMetric],
    *,
    existing_cases: Sequence[Dict[str, Any]] = (),
    on_case: Callable[[List[Dict[str, Any]]], None] | None = None,
) -> Dict[str, Any]:
    """Score samples, optionally resuming and checkpointing after every case."""
    expected = set(METRIC_LABELS)
    if set(metrics) != expected:
        raise ValueError(f"metrics must be exactly: {', '.join(sorted(expected))}")
    existing_by_id = {
        str(case.get("id", "")): dict(case) for case in existing_cases
    }
    if len(existing_by_id) != len(existing_cases) or "" in existing_by_id:
        raise ValueError("Existing scored cases must have unique non-empty ids")
    cases: List[Dict[str, Any]] = []
    for sample in samples:
        existing = existing_by_id.get(str(sample.get("id", "")))
        if existing is not None and set(existing.get("scores", {})) == expected:
            cases.append(existing)
            continue
        try:
            context_result = await metrics["context_relevance"].ascore(
                user_input=sample["user_input"],
                retrieved_contexts=sample["retrieved_contexts"],
            )
            faithfulness_result = await metrics["faithfulness"].ascore(
                user_input=sample["user_input"],
                response=sample["response"],
                retrieved_contexts=sample["retrieved_contexts"],
            )
            relevance_result = await metrics["answer_relevance"].ascore(
                user_input=sample["user_input"],
                response=sample["response"],
            )
        except Exception as exc:
            raise RuntimeError(f"RAGAS scoring failed for {sample['id']}: {exc}") from exc
        scores = {
            "context_relevance": _score_value(context_result),
            "faithfulness": _score_value(faithfulness_result),
            "answer_relevance": _score_value(relevance_result),
        }
        cases.append({**sample, "scores": scores})
        if on_case is not None:
            on_case(cases)

    aggregates = {
        name: sum(case["scores"][name] for case in cases) / len(cases)
        for name in METRIC_LABELS
    }
    return {"metrics": aggregates, "cases": cases}


def _score_value(result: Any) -> float:
    value = getattr(result, "value", result)
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"RAGAS returned a non-numeric score: {value!r}") from exc
    if not -1.0 <= score <= 1.0:
        raise RuntimeError(f"RAGAS returned an out-of-range score: {score}")
    return score


def print_report(result: Dict[str, Any], *, show_cases: bool = False) -> None:
    print("RAGAS Evaluation")
    print("=" * 72)
    print(
        f"Evaluated: {result['evaluated_cases']} answerable cases | "
        f"excluded no-answer cases: {result['skipped_unanswerable']}"
    )
    for name, label in METRIC_LABELS.items():
        print(f"{label} ({name}): {result['metrics'][name]:.3f}")
    print(
        f"Retriever modes: {result['retrieval_mode_counts']} | "
        f"judge: {result['judge_model']}"
    )
    if show_cases:
        print("\nPer-case scores")
        print("-" * 72)
        for case in result["cases"]:
            scores = case["scores"]
            print(
                f"{case['id']:<26} context={scores['context_relevance']:.3f} "
                f"faith={scores['faithfulness']:.3f} "
                f"answer={scores['answer_relevance']:.3f}"
            )


def _select_rows(
    rows: Sequence[Dict[str, Any]], case_ids: Sequence[str]
) -> List[Dict[str, Any]]:
    if not case_ids:
        return list(rows)
    requested = set(case_ids)
    known = {row["id"] for row in rows}
    unknown = sorted(requested - known)
    if unknown:
        raise ValueError(f"Unknown case ids: {', '.join(unknown)}")
    return [row for row in rows if row["id"] in requested]


def _generation_config(args: argparse.Namespace) -> Dict[str, Any]:
    generation = {
        "dataset_sha256": file_sha256(args.dataset),
        "knowledge_sha256": knowledge_sha256(args.knowledge_dir),
        "retriever_backend": args.retriever_backend,
        "top_k": args.top_k,
        "threshold": args.threshold,
        "embedding_model": args.embedding_model,
        # The same local model may live under different absolute paths on two PCs.
        "generator_model": Path(str(config.model_path)).name,
        "case_ids": sorted(set(args.case_id or [])),
    }
    if args.retriever_backend == "milvus":
        generation["milvus"] = {
            "collection_name": config.milvus_collection_name,
            "index_type": config.milvus_index_type,
            "nlist": config.milvus_nlist,
            "nprobe": config.milvus_nprobe,
        }
    return generation


def _judge_config(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "judge_model": args.judge_model,
        "judge_embedding_model": args.judge_embedding_model,
        "judge_embedding_provider": args.judge_embedding_provider,
        "judge_base_url": args.judge_base_url,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--knowledge-dir", type=Path, default=DEFAULT_KNOWLEDGE_DIR)
    parser.add_argument("--top-k", type=int, default=config.retriever_top_k)
    parser.add_argument("--threshold", type=float, default=config.retriever_threshold)
    parser.add_argument("--embedding-model", default=config.embedding_model)
    parser.add_argument(
        "--retriever-backend",
        choices=("memory", "milvus"),
        default="memory",
        help="Evaluation retriever; Milvus is direct and never silently falls back",
    )
    parser.add_argument(
        "--judge-model",
        default=os.getenv("RAGAS_JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
    )
    parser.add_argument(
        "--judge-embedding-model",
        default=os.getenv(
            "RAGAS_JUDGE_EMBEDDING_MODEL", DEFAULT_JUDGE_EMBEDDING_MODEL
        ),
    )
    parser.add_argument(
        "--judge-embedding-provider",
        choices=("openai", "huggingface"),
        default=os.getenv(
            "RAGAS_JUDGE_EMBEDDING_PROVIDER",
            DEFAULT_JUDGE_EMBEDDING_PROVIDER,
        ),
        help="Use OpenAI-compatible embeddings or a local Hugging Face model",
    )
    parser.add_argument("--judge-base-url", default=os.getenv("OPENAI_BASE_URL"))
    parser.add_argument(
        "--stage",
        choices=("all", "generate", "score"),
        default="all",
        help="Run both stages, generation only, or score an existing progress file",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=DEFAULT_PROGRESS_FILE,
        help="Atomic JSON checkpoint; an existing compatible file resumes automatically",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Discard an existing checkpoint and start a new generation run",
    )
    parser.add_argument(
        "--max-new-cases",
        type=int,
        help="Generate at most this many unfinished cases in the current invocation",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        help="Restrict the run to one or more case ids; may be repeated",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show-cases", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.top_k <= 100:
        parser.error("--top-k must be between 1 and 100")
    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")
    if args.max_new_cases is not None and args.max_new_cases < 1:
        parser.error("--max-new-cases must be positive")
    if args.stage == "score" and args.fresh:
        parser.error("--fresh cannot be used with --stage score")
    if args.stage in {"all", "generate"} and config.llm_mock:
        parser.error("LLM_MOCK must be disabled; mock answers make RAGAS scores invalid")

    try:
        rows = _select_rows(load_rows(args.dataset), args.case_id or [])
        expected_answerable = sum(bool(row["answerable"]) for row in rows)
        skipped_unanswerable = sum(not row["answerable"] for row in rows)
        generation_config = _generation_config(args)
        if args.progress_file.exists() and not args.fresh:
            progress = load_progress(args.progress_file)
            validate_progress_config(progress, generation_config)
        else:
            if args.stage == "score":
                raise ValueError(
                    f"Progress file not found for scoring: {args.progress_file}"
                )
            progress = {
                "schema_version": PROGRESS_SCHEMA_VERSION,
                "status": "new",
                "config": generation_config,
                "expected_answerable_cases": expected_answerable,
                "skipped_unanswerable": skipped_unanswerable,
                "retrieval_mode_counts": {},
                "samples": [],
            }
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.stage in {"all", "generate"}:
        retriever = build_retriever(args.retriever_backend, args.embedding_model)
        ingestion = load_knowledge(retriever, args.knowledge_dir)
        progress["ingestion"] = ingestion

        def checkpoint_generation(
            samples: List[Dict[str, Any]], mode_counts: Dict[str, int]
        ) -> None:
            progress["status"] = "generating"
            progress["samples"] = samples
            progress["retrieval_mode_counts"] = mode_counts
            save_progress(args.progress_file, progress)

        collected = collect_samples(
            rows,
            retriever,
            top_k=args.top_k,
            threshold=args.threshold,
            answer_generator=generate_with_project_rag,
            existing_samples=progress["samples"],
            max_new_cases=args.max_new_cases,
            on_sample=checkpoint_generation,
        )
        progress["samples"] = collected["samples"]
        progress["retrieval_mode_counts"] = collected["retrieval_mode_counts"]
        generation_complete = len(collected["samples"]) == expected_answerable
        progress["status"] = "generated" if generation_complete else "generation_partial"
        save_progress(args.progress_file, progress)

        if args.stage == "generate":
            if args.json:
                print(json.dumps(progress, ensure_ascii=False, indent=2))
            else:
                print(
                    f"Generation checkpoint: {len(collected['samples'])}/"
                    f"{expected_answerable} cases | new: {collected['new_cases']} | "
                    f"file: {args.progress_file}"
                )
            return 0

    samples = list(progress["samples"])
    if not samples:
        parser.error("Progress file contains no generated samples to score")
    judge_config = _judge_config(args)
    existing_scored = [sample for sample in samples if "scores" in sample]
    if existing_scored and progress.get("judge_config") != judge_config:
        parser.error(
            "Judge configuration does not match existing scores; use a new "
            "--progress-file or restart with --fresh"
        )
    progress["judge_config"] = judge_config
    metrics = build_ragas_metrics(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        judge_model=args.judge_model,
        embedding_model=args.judge_embedding_model,
        embedding_provider=args.judge_embedding_provider,
        base_url=args.judge_base_url,
    )

    def checkpoint_scoring(cases: List[Dict[str, Any]]) -> None:
        scored_by_id = {case["id"]: case for case in cases}
        progress["status"] = "scoring"
        progress["samples"] = [
            scored_by_id.get(sample["id"], sample) for sample in samples
        ]
        save_progress(args.progress_file, progress)

    scored = asyncio.run(
        evaluate_with_ragas(
            samples,
            metrics,
            existing_cases=existing_scored,
            on_case=checkpoint_scoring,
        )
    )
    result = {
        "evaluated_cases": len(scored["cases"]),
        "expected_answerable_cases": expected_answerable,
        "skipped_unanswerable": skipped_unanswerable,
        "retrieval_mode_counts": progress["retrieval_mode_counts"],
        "retriever_backend": args.retriever_backend,
        "top_k": args.top_k,
        "threshold": args.threshold,
        "generator_model": config.model_path,
        "judge_model": args.judge_model,
        "judge_embedding_model": args.judge_embedding_model,
        "judge_embedding_provider": args.judge_embedding_provider,
        "ingestion": progress.get("ingestion", {}),
        **scored,
    }
    progress["samples"] = scored["cases"]
    progress["metrics"] = scored["metrics"]
    progress["status"] = (
        "complete"
        if len(scored["cases"]) == expected_answerable
        else "scoring_partial"
    )
    save_progress(args.progress_file, progress)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result, show_cases=args.show_cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

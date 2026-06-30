"""Evaluate router intent classification on a JSONL dataset."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.graph.router import classify_intent_with_scores, get_llm_router_metrics

DEFAULT_DATASET = Path("data/eval/router_eval.jsonl")
INTENTS = ["chat", "search", "diet", "motion", "mcp"]


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
            if not isinstance(row.get("text"), str) or not row["text"].strip():
                raise ValueError(f"Line {line_no} must include non-empty text")
            if row.get("intent") not in INTENTS:
                raise ValueError(
                    f"Line {line_no} has invalid intent {row.get('intent')!r}"
                )
            rows.append(row)
    return rows


def evaluate(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    get_llm_router_metrics(reset=True)
    cases = []
    labels = set(INTENTS)
    total = 0
    correct = 0
    confusion: Dict[str, Counter[str]] = defaultdict(Counter)
    support = Counter()
    predicted_counts = Counter()
    source_counts = Counter()
    category_support = Counter()
    category_correct = Counter()
    ambiguity_counts = Counter()
    multi_intent_total = 0
    secondary_exact = 0
    route_plan_exact = 0

    for row in rows:
        expected = row["intent"]
        decision = classify_intent_with_scores(row["text"])
        predicted = decision["intent"]
        is_correct = predicted == expected
        total += 1
        correct += int(is_correct)
        labels.add(expected)
        labels.add(predicted)
        confusion[expected][predicted] += 1
        support[expected] += 1
        predicted_counts[predicted] += 1
        source_counts[decision["source"]] += 1
        category = row.get("category", "uncategorized")
        category_support[category] += 1
        category_correct[category] += int(is_correct)
        ambiguity_signals = decision.get("ambiguity_signals", [])
        ambiguity_counts.update(ambiguity_signals)
        predicted_secondary = decision.get("secondary_intents", [])
        predicted_route_plan = decision.get("route_plan", [predicted])
        expected_secondary = row.get("secondary_intents")
        expected_route_plan = row.get("route_plan")
        if expected_secondary is not None and expected_route_plan is not None:
            multi_intent_total += 1
            secondary_exact += int(predicted_secondary == expected_secondary)
            route_plan_exact += int(predicted_route_plan == expected_route_plan)
        cases.append({
            "text": row["text"],
            "expected": expected,
            "predicted": predicted,
            "correct": is_correct,
            "confidence": decision["confidence"],
            "source": decision["source"],
            "reason": decision["reason"],
            "category": category,
            "note": row.get("note", ""),
            "ambiguity_signals": ambiguity_signals,
            "primary_intent": decision.get("primary_intent", predicted),
            "secondary_intents": predicted_secondary,
            "route_plan": predicted_route_plan,
            "needs_clarification": decision.get("needs_clarification", False),
            "secondary_exact": (
                predicted_secondary == expected_secondary
                if expected_secondary is not None
                else None
            ),
            "route_plan_exact": (
                predicted_route_plan == expected_route_plan
                if expected_route_plan is not None
                else None
            ),
        })

    per_intent = {}
    for intent in sorted(labels):
        tp = confusion[intent][intent]
        fp = sum(confusion[other][intent] for other in labels if other != intent)
        fn = sum(count for pred, count in confusion[intent].items() if pred != intent)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        per_intent[intent] = {
            "support": support[intent],
            "predicted": predicted_counts[intent],
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "per_intent": per_intent,
        "confusion": {
            expected: dict(preds) for expected, preds in sorted(confusion.items())
        },
        "by_category": {
            category: {
                "support": category_support[category],
                "correct": category_correct[category],
                "accuracy": (
                    category_correct[category] / category_support[category]
                    if category_support[category]
                    else 0.0
                ),
            }
            for category in sorted(category_support)
        },
        "source_counts": dict(source_counts),
        "ambiguity_counts": dict(ambiguity_counts),
        "multi_intent_metrics": {
            "annotated_cases": multi_intent_total,
            "secondary_exact": secondary_exact,
            "secondary_exact_accuracy": (
                secondary_exact / multi_intent_total if multi_intent_total else 0.0
            ),
            "route_plan_exact": route_plan_exact,
            "route_plan_exact_accuracy": (
                route_plan_exact / multi_intent_total if multi_intent_total else 0.0
            ),
        },
        "llm_router_metrics": get_llm_router_metrics(),
        "mismatches": [case for case in cases if not case["correct"]],
        "cases": cases,
    }


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def print_text_report(result: Dict[str, Any], show_cases: bool) -> None:
    print("Router Eval")
    print("=" * 72)
    print(
        f"Total: {result['total']} | Correct: {result['correct']} | "
        f"Accuracy: {_pct(result['accuracy'])}"
    )
    print()
    print("Per-intent metrics")
    print("-" * 72)
    print(f"{'intent':<10} {'support':>7} {'pred':>7} {'precision':>10} {'recall':>8} {'f1':>8}")
    for intent, metrics in result["per_intent"].items():
        print(
            f"{intent:<10} {metrics['support']:>7} {metrics['predicted']:>7} "
            f"{_pct(metrics['precision']):>10} {_pct(metrics['recall']):>8} "
            f"{_pct(metrics['f1']):>8}"
        )
    print()
    print("Evaluation slices")
    print("-" * 72)
    print(f"{'category':<24} {'support':>7} {'correct':>8} {'accuracy':>10}")
    for category, metrics in result["by_category"].items():
        print(
            f"{category:<24} {metrics['support']:>7} "
            f"{metrics['correct']:>8} {_pct(metrics['accuracy']):>10}"
        )
    print()
    print("Route source counts")
    print("-" * 72)
    for source, count in sorted(result["source_counts"].items()):
        print(f"{source:<20} {count}")
    print()
    print("Ambiguity signals")
    print("-" * 72)
    if result["ambiguity_counts"]:
        for signal, count in sorted(result["ambiguity_counts"].items()):
            print(f"{signal:<28} {count}")
    else:
        print("none")
    print()
    print("Multi-intent metrics")
    print("-" * 72)
    multi_metrics = result["multi_intent_metrics"]
    print(
        f"annotated={multi_metrics['annotated_cases']} "
        f"secondary_exact={multi_metrics['secondary_exact']} "
        f"({_pct(multi_metrics['secondary_exact_accuracy'])}) "
        f"route_plan_exact={multi_metrics['route_plan_exact']} "
        f"({_pct(multi_metrics['route_plan_exact_accuracy'])})"
    )
    print()
    print("LLM router metrics")
    print("-" * 72)
    metrics = result["llm_router_metrics"]
    print(
        f"calls={metrics['calls']} average_latency_ms={metrics['average_latency_ms']:.2f} "
        f"max_latency_ms={metrics['max_latency_ms']:.2f}"
    )
    for outcome, count in sorted(metrics["outcomes"].items()):
        print(f"{outcome:<20} {count}")
    for outcome, count in sorted(metrics["selection_outcomes"].items()):
        print(f"selection:{outcome:<30} {count}")
    print()
    print("Confusion matrix")
    print("-" * 72)
    for expected, preds in result["confusion"].items():
        cells = ", ".join(f"{pred}:{count}" for pred, count in sorted(preds.items()))
        print(f"{expected:<10} -> {cells}")

    if result["mismatches"]:
        print()
        print("Mismatches")
        print("-" * 72)
        for case in result["mismatches"]:
            print(
                f"[{case['expected']} -> {case['predicted']}] "
                f"conf={case['confidence']:.2f} source={case['source']} "
                f"text={case['text']}"
            )
            if case["note"]:
                print(f"  note: {case['note']}")
            print(f"  reason: {case['reason']}")

    if show_cases:
        print()
        print("All cases")
        print("-" * 72)
        for case in result["cases"]:
            status = "OK" if case["correct"] else "FAIL"
            print(
                f"{status:<4} expected={case['expected']:<7} "
                f"predicted={case['predicted']:<7} "
                f"conf={case['confidence']:.2f} source={case['source']:<18} "
                f"text={case['text']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"Router eval JSONL path. Default: {DEFAULT_DATASET}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a text report.",
    )
    parser.add_argument(
        "--show-cases",
        action="store_true",
        help="Include every evaluated case in the text report.",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit with code 1 when any case is misclassified.",
    )
    args = parser.parse_args()

    rows = load_rows(args.dataset)
    result = evaluate(rows)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_text_report(result, show_cases=args.show_cases)

    if args.fail_on_mismatch and result["mismatches"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

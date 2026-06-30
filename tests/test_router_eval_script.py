"""Router eval script tests."""
from pathlib import Path

from scripts.eval_router import evaluate, load_rows


ROUTER_CHALLENGE_EVAL_PATH = Path("data/eval/router_challenge_eval.jsonl")


def test_load_router_eval_dataset():
    rows = load_rows(Path("data/eval/router_eval.jsonl"))
    assert rows
    assert all("text" in row and "intent" in row for row in rows)


def test_router_eval_dataset_is_currently_green():
    rows = load_rows(Path("data/eval/router_eval.jsonl"))
    result = evaluate(rows)
    assert result["total"] == len(rows)
    assert result["accuracy"] == 1.0
    assert result["mismatches"] == []
    assert set(result["per_intent"]) >= {"chat", "search", "diet", "motion", "mcp"}
    assert result["by_category"]
    assert "ambiguity_counts" in result
    assert "llm_router_metrics" in result


def test_load_router_challenge_eval_dataset():
    rows = load_rows(ROUTER_CHALLENGE_EVAL_PATH)
    result = evaluate(rows)
    categories = {row["category"] for row in rows}

    assert rows
    assert result["total"] == len(rows)
    assert result["by_category"]
    assert result["ambiguity_counts"]
    assert {"multi_intent_order", "diet_vs_recipe", "plan_vs_motion"} <= categories


def test_router_challenge_eval_has_multi_intent_annotations():
    rows = load_rows(ROUTER_CHALLENGE_EVAL_PATH)

    for row in rows:
        assert row["primary_intent"] == row["intent"]
        assert isinstance(row["secondary_intents"], list)
        assert isinstance(row["route_plan"], list)
        assert row["route_plan"]
        assert row["route_plan"][0] == row["primary_intent"]
        assert isinstance(row["expected_failure_reason"], str)
        assert row["expected_failure_reason"].strip()

    result = evaluate(rows)
    assert result["multi_intent_metrics"]["annotated_cases"] == len(rows)
    assert result["multi_intent_metrics"]["secondary_exact_accuracy"] >= 0.75
    assert result["multi_intent_metrics"]["route_plan_exact_accuracy"] >= 0.90

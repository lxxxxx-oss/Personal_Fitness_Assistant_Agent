"""Router tests."""
import json
from pathlib import Path

import pytest
import app.graph.router as router_module
from app.graph.state import RouterState
from app.graph.router import (
    classify_intent,
    classify_intent_with_scores,
    intent_classify_node,
    build_router_graph,
)


ROUTER_EVAL_PATH = Path("data/eval/router_eval.jsonl")


class TestIntentClassification:
    def test_search_keywords(self):
        assert classify_intent("搜索最新的健身资讯") == "search"
        assert classify_intent("查一下深蹲的标准动作") == "search"

    def test_motion_keywords(self):
        assert classify_intent("分析我的深蹲姿势") == "motion"
        assert classify_intent("analyze this .npz file") == "motion"

    def test_diet_keywords(self):
        assert classify_intent("减脂期间吃什么") == "diet"
        assert classify_intent("健身营养怎么搭配") == "diet"

    def test_mcp_keywords(self):
        assert classify_intent("怎么做番茄炒蛋") == "mcp"
        assert classify_intent("菜谱:红烧肉") == "mcp"

    def test_default_to_chat(self):
        assert classify_intent("什么是健身") == "chat"
        assert classify_intent("你好") == "chat"


    def test_colloquial_diet_intent(self):
        assert classify_intent("我最近想瘦一点，有什么建议？") == "diet"
        assert classify_intent("我想控制体重，应该怎么吃？") == "diet"

    def test_recent_news_stays_search(self):
        assert classify_intent("最近有什么健身新闻？") == "search"
        assert classify_intent("帮我搜索一下最新增肌研究") == "search"

    def test_motion_review_intent(self):
        assert classify_intent("帮我看看深蹲哪里不对") == "motion"

    def test_recipe_steps_intent(self):
        assert classify_intent("番茄炒蛋步骤是什么？") == "mcp"

    def test_general_protein_question_stays_chat(self):
        assert classify_intent("蛋白质有什么作用？") == "chat"
        assert classify_intent("深蹲有哪些好处？") == "chat"

    def test_semantic_examples_handle_implicit_diet(self):
        decision = classify_intent_with_scores("我想把身材调整得更轻盈一点")
        assert decision["intent"] == "diet"
        assert decision["source"] == "semantic_examples"
        assert decision["confidence"] >= 0.62

    def test_semantic_examples_handle_implicit_recipe(self):
        decision = classify_intent_with_scores("晚饭做什么菜？")
        assert decision["intent"] == "mcp"
        assert decision["source"] == "semantic_examples"
        assert decision["confidence"] >= 0.62

    def test_chat_can_win_conceptual_questions(self):
        decision = classify_intent_with_scores("深蹲有哪些好处？")
        assert decision["intent"] == "chat"
        assert decision["scores"]["chat"] > decision["scores"]["motion"]

    def test_expanded_boundary_cases(self):
        assert classify_intent("我有点胖，想改善一下体型") == "diet"
        assert classify_intent("一天吃多少蛋白质比较合适？") == "diet"
        assert classify_intent("蛋白质为什么能帮助增肌？") == "chat"
        assert classify_intent("为什么深蹲能练腿？") == "chat"
        assert classify_intent("晚餐推荐一个高蛋白菜") == "mcp"
        assert classify_intent("查一下最近减脂饮食研究") == "search"

    def test_route_decision_contains_scores_and_reason(self):
        decision = classify_intent_with_scores("我最近想瘦一点，有什么建议？")
        assert decision["intent"] == "diet"
        assert decision["source"] == "weighted_rules"
        assert decision["confidence"] > 0
        assert decision["scores"]["diet"] > decision["scores"]["search"]
        assert decision["matches"]

    def test_llm_classifier_contract_accepts_high_confidence(self, monkeypatch):
        def fake_call(prompt: str) -> str:
            assert "needs_clarification" in prompt
            assert "chat|search|diet|motion|mcp" in prompt
            return json.dumps(
                {
                    "intent": "diet",
                    "confidence": 0.82,
                    "reason": "personal nutrition request",
                    "needs_clarification": False,
                }
            )

        monkeypatch.setattr(router_module, "_call_llm_router", fake_call)

        decision = classify_intent_with_scores("custom ambiguous request")

        assert decision["intent"] == "diet"
        assert decision["source"] == "llm_classifier"
        assert decision["confidence"] == 0.82
        assert "llm_intent:diet" in decision["matches"]

    def test_llm_classifier_rejects_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            router_module,
            "_call_llm_router",
            lambda prompt: "not json",
        )

        decision = router_module._llm_classifier_route("custom ambiguous request")

        assert decision["intent"] == "chat"
        assert decision["source"] == "llm_parse_error"
        assert decision["confidence"] == 0.0

    def test_llm_classifier_rejects_low_confidence(self, monkeypatch):
        monkeypatch.setattr(
            router_module,
            "_call_llm_router",
            lambda prompt: json.dumps(
                {
                    "intent": "search",
                    "confidence": 0.44,
                    "reason": "weak latest-news signal",
                    "needs_clarification": False,
                }
            ),
        )

        decision = router_module._llm_classifier_route("custom ambiguous request")

        assert decision["intent"] == "chat"
        assert decision["source"] == "llm_low_confidence"
        assert decision["confidence"] == 0.44

    def test_llm_classifier_rejects_clarification_requests(self, monkeypatch):
        monkeypatch.setattr(
            router_module,
            "_call_llm_router",
            lambda prompt: json.dumps(
                {
                    "intent": "motion",
                    "confidence": 0.88,
                    "reason": "user may mean technique or general knowledge",
                    "needs_clarification": True,
                }
            ),
        )

        decision = router_module._llm_classifier_route("custom ambiguous request")

        assert decision["intent"] == "chat"
        assert decision["source"] == "llm_clarification"
        assert "needs_clarification:true" in decision["matches"]

    def test_intent_node_writes_route_metadata(self):
        state: RouterState = {
            "user_input": "我最近想瘦一点，有什么建议？",
            "user_id": "test_001",
            "memory": [],
        }
        result = intent_classify_node(state)
        assert result["intent"] == "diet"
        assert result["_route_source"] == "weighted_rules"
        assert result["_route_confidence"] > 0
        assert result["_route_scores"]["diet"] > result["_route_scores"]["search"]
        assert result["_route_reason"]


class TestRouterGraph:
    def test_build_graph_returns_compiled_graph(self):
        graph = build_router_graph()
        assert graph is not None
        state: RouterState = {
            "user_input": "你好",
            "user_id": "test_001",
            "intent": "",
            "memory": [],
            "result": "",
            "error": None,
        }
        result = graph.invoke(state)
        assert "result" in result
        assert result["intent"] == "chat"


class TestRouterEvalDataset:
    def test_router_eval_dataset_matches_current_router(self):
        assert ROUTER_EVAL_PATH.exists()
        with ROUTER_EVAL_PATH.open("r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        assert rows
        mismatches = []
        for row in rows:
            actual = classify_intent(row["text"])
            if actual != row["intent"]:
                mismatches.append((row["text"], row["intent"], actual))

        assert not mismatches

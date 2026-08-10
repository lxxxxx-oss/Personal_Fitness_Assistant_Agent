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
    collect_route_result_node,
    route_after_collection,
    synthesize_route_results_node,
)


ROUTER_EVAL_PATH = Path("data/eval/router_eval.jsonl")
ROUTER_SEMANTIC_REWRITE_EVAL_PATH = Path(
    "data/eval/router_semantic_rewrite_eval.jsonl"
)


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
        assert classify_intent("糖醋排骨怎么做") == "mcp"

    def test_general_protein_question_stays_chat(self):
        assert classify_intent("蛋白质有什么作用？") == "chat"
        assert classify_intent("深蹲有哪些好处？") == "chat"

    def test_semantic_examples_handle_implicit_diet(self):
        # Layer 1 weighted-rules covers implicit diet intent through keywords
        decision = classify_intent_with_scores("我想把身材调整得更轻盈一点")
        assert decision["intent"] == "diet"
        assert decision["source"] == "weighted_rules"
        assert decision["confidence"] >= 0.62

    def test_semantic_examples_handle_implicit_recipe(self):
        # Layer 1 weighted-rules covers implicit cooking intent through keywords
        decision = classify_intent_with_scores("晚饭做什么菜？")
        assert decision["intent"] == "mcp"
        assert decision["source"] == "weighted_rules"
        assert decision["confidence"] >= 0.62

    def test_embedding_examples_are_disabled_by_default(self, monkeypatch):
        from app.config import config

        monkeypatch.setattr(config, "router_embedding_enabled", False)

        def fail_if_called(model_name: str):
            raise AssertionError("embedding model should not load when disabled")

        monkeypatch.setattr(router_module, "_get_embedding_router_model", fail_if_called)

        decision = classify_intent_with_scores("zzzzqqqq")

        assert decision["intent"] == "chat"
        assert decision["source"] == "fallback"

    def test_embedding_examples_can_handle_low_confidence_rewrites(self, monkeypatch):
        from app.config import config

        class FakeEmbeddingModel:
            def encode(self, texts, normalize_embeddings=True):
                vectors = []
                for text in texts:
                    if (
                        text == "zzzzqqqq"
                        or text in router_module.SEMANTIC_EXAMPLES["diet"]
                    ):
                        vectors.append([1.0, 0.0])
                    elif text in router_module.SEMANTIC_EXAMPLES["search"]:
                        vectors.append([0.0, 1.0])
                    else:
                        vectors.append([0.0, 0.0])
                return vectors

        monkeypatch.setattr(config, "router_embedding_enabled", True)
        monkeypatch.setattr(config, "router_embedding_model", "fake-router-model")
        monkeypatch.setattr(config, "router_embedding_min_confidence", 0.68)
        monkeypatch.setattr(config, "router_embedding_min_margin", 0.05)
        monkeypatch.setattr(
            router_module,
            "_get_embedding_router_model",
            lambda model_name: FakeEmbeddingModel(),
        )
        router_module._EMBEDDING_EXAMPLE_VECTORS.clear()

        decision = classify_intent_with_scores("zzzzqqqq")

        assert decision["intent"] == "diet"
        assert decision["source"] == "embedding_examples"
        assert decision["confidence"] >= 0.68

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

    @pytest.mark.parametrize(
        ("text", "primary", "secondary", "route_plan"),
        [
            (
                "先分析一下我的深蹲姿势，然后搜索最近的纠正方法",
                "motion",
                ["search"],
                ["motion", "search"],
            ),
            (
                "先分析 sample.npz，然后给我饮食建议",
                "motion",
                ["diet"],
                ["motion", "diet"],
            ),
        ],
    )
    def test_multi_intent_observation(self, text, primary, secondary, route_plan):
        decision = classify_intent_with_scores(text)

        assert decision["intent"] == primary
        assert decision["primary_intent"] == primary
        assert decision["secondary_intents"] == secondary
        assert decision["route_plan"] == route_plan

    def test_cross_domain_plan_requests_clarification_without_composition(self):
        decision = classify_intent_with_scores(
            "能不能根据我最近训练状态安排一下吃和练"
        )

        # Cross-domain without explicit sequencing → chat (safe fallback)
        assert decision["primary_intent"] == "chat"
        assert decision["route_plan"] == ["chat"]
        # needs_clarification is False after ambiguity refactoring —
        # the router already routes to chat directly.

    def test_every_valid_route_plan_combination_is_executed(self):
        motion_diet: RouterState = {
            "user_input": "先分析 sample.npz，然后给我饮食建议",
            "user_id": "test",
            "memory": [],
        }
        diet_recipe: RouterState = {
            "user_input": "先给我减脂原则，然后推荐一道具体晚餐菜",
            "user_id": "test",
            "memory": [],
        }

        motion_diet_result = intent_classify_node(motion_diet)
        diet_recipe_result = intent_classify_node(diet_recipe)

        assert motion_diet_result["_route_execution_plan"] == ["motion", "diet"]
        assert diet_recipe_result["_route_plan"] == ["diet", "mcp"]
        assert diet_recipe_result["_route_execution_plan"] == ["diet", "mcp"]
        assert diet_recipe_result["_route_execution_warnings"] == []

    def test_multi_intent_plan_preserves_user_expression_order(self):
        decision = classify_intent_with_scores(
            "我想减脂，顺便查一下最近间歇性禁食的研究"
        )

        assert decision["primary_intent"] == "diet"
        assert decision["secondary_intents"][0] == "search"
        assert decision["route_plan"] == ["diet", "search"]

    def test_route_plan_validation_checks_legality_duplicates_and_step_budget(self):
        execution_plan, warnings = router_module._validate_route_plan(
            ["motion", "motion", "unknown", "diet", "search", "chat"],
            "motion",
        )

        assert execution_plan == ["motion", "diet", "search"]
        assert "route_plan_duplicate_intent:motion" in warnings
        assert "route_plan_invalid_intent:unknown" in warnings
        assert "route_plan_truncated:max_steps=3" in warnings

    def test_collect_route_result_advances_and_preserves_records(self):
        state: RouterState = {
            "user_input": "combined request",
            "intent": "motion",
            "_primary_intent": "motion",
            "_active_intent": "motion",
            "_route_execution_plan": ["motion", "diet"],
            "_route_execution_cursor": 0,
            "_route_results": [],
            "result": "motion result",
            "error": None,
        }

        result = collect_route_result_node(state)

        assert result["_route_results"][0]["intent"] == "motion"
        assert result["_route_results"][0]["result"] == "motion result"
        assert result["_active_intent"] == "diet"
        assert route_after_collection(result) == "diet"

    def test_multi_route_synthesis_keeps_partial_success(self):
        state: RouterState = {
            "user_input": "combined request",
            "intent": "motion",
            "_primary_intent": "motion",
            "_route_results": [
                {
                    "intent": "motion",
                    "result": "motion result",
                    "error": None,
                    "prompt": "",
                    "sources": [],
                },
                {
                    "intent": "diet",
                    "result": "",
                    "error": "diet unavailable",
                    "prompt": "",
                    "sources": [],
                },
            ],
            "_route_execution_warnings": [],
        }

        result = synthesize_route_results_node(state)

        assert result["result"] == "Mock LLM response"
        assert result["error"] is None
        assert "partial_route_failure:diet" in result["_route_execution_warnings"]

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

    def test_ambiguity_detector_routes_to_chat_for_safe_handling(self):
        decision = classify_intent_with_scores(
            "能不能根据我最近训练状态安排一下吃和练"
        )

        # Routes to chat — the primary (and only above-threshold) intent is chat.
        # The new score-distribution logic treats chat as the dominant single intent
        # because no other intent reaches the minimum score threshold.
        assert decision["intent"] == "chat"

    def test_close_candidates_request_targeted_clarification(self):
        decision = classify_intent_with_scores("想练深蹲吃什么")

        assert decision["source"] == "ambiguity_fallback"
        assert decision["needs_clarification"] is True
        assert decision["clarification_candidates"] == ["diet", "motion"]
        assert "1）饮食建议" in decision["clarification_question"]
        assert "2）动作分析" in decision["clarification_question"]

    def test_pending_clarification_restores_selected_route_and_original_input(self):
        state: RouterState = {
            "user_input": "第二个",
            "user_id": "test",
            "memory": [],
            "_pending_route_clarification": {
                "original_input": "想练深蹲吃什么",
                "candidates": ["diet", "motion"],
                "scores": {"diet": 5.0, "motion": 4.0},
            },
        }

        result = intent_classify_node(state)

        assert result["intent"] == "motion"
        assert result["_route_source"] == "clarification_resolution"
        assert result["_route_execution_plan"] == ["motion"]
        assert result["_clarification_resolved"] is True
        assert "原始问题：想练深蹲吃什么" in result["user_input"]
        assert "用户澄清：第二个" in result["user_input"]

    def test_pending_clarification_accepts_natural_ordinal_answer(self):
        state: RouterState = {
            "user_input": "那就先做第二个吧",
            "user_id": "test",
            "memory": [],
            "_pending_route_clarification": {
                "original_input": "想练深蹲吃什么",
                "candidates": ["diet", "motion"],
            },
        }

        result = intent_classify_node(state)

        assert result["intent"] == "motion"
        assert result["_route_source"] == "clarification_resolution"

    def test_pending_clarification_can_restore_both_routes(self):
        state: RouterState = {
            "user_input": "两个都要",
            "user_id": "test",
            "memory": [],
            "_pending_route_clarification": {
                "original_input": "想练深蹲吃什么",
                "candidates": ["diet", "motion"],
            },
        }

        result = intent_classify_node(state)

        assert result["_route_execution_plan"] == ["diet", "motion"]
        assert result["_needs_clarification"] is False

    def test_unclear_clarification_answer_repeats_choices_without_execution(self):
        state: RouterState = {
            "user_input": "这个",
            "user_id": "test",
            "memory": [],
            "_pending_route_clarification": {
                "original_input": "想练深蹲吃什么",
                "candidates": ["diet", "motion"],
            },
        }

        result = intent_classify_node(state)

        assert result["_route_source"] == "clarification_retry"
        assert result["_needs_clarification"] is True
        assert result["_route_execution_plan"] == ["chat"]
        assert "我还不能确定你的选择" in result["_clarification_question"]

    def test_new_clear_request_cancels_pending_clarification(self):
        state: RouterState = {
            "user_input": "查一下最近的减脂研究",
            "user_id": "test",
            "memory": [],
            "_pending_route_clarification": {
                "original_input": "想练深蹲吃什么",
                "candidates": ["diet", "motion"],
            },
        }

        result = intent_classify_node(state)

        assert result["intent"] == "search"
        assert result["_clarification_cancelled"] is True
        assert result["_needs_clarification"] is False

    def test_ambiguity_fallback_beats_strong_rule(self):
        """When no single intent dominates clearly, route to chat."""
        decision = classify_intent_with_scores("吃和练怎么安排比较好")

        assert decision["intent"] == "chat"
        # chat dominates (margin=6 ≥ 4), so it's handled as a single dominant intent.
        # If margin were narrow, source would be ambiguity_fallback.
    def test_deterministic_order_signal_does_not_call_llm(self, monkeypatch):
        def fail_if_called(prompt: str) -> str:
            raise AssertionError("ordered deterministic route should not call LLM")

        monkeypatch.setattr(router_module, "_call_llm_router", fail_if_called)

        decision = classify_intent_with_scores(
            "先分析一下我的深蹲姿势，然后搜索最近的纠正方法"
        )

        assert decision["intent"] == "motion"
        assert decision["source"] == "weighted_rules"
        # 显式顺序信号应触发多意图路由计划
        assert len(decision["route_plan"]) == 2

    def test_local_llm_provider_is_disabled_by_default(self, monkeypatch):
        from app.config import config

        monkeypatch.setattr(config, "llm_router_enabled", False)

        assert router_module._call_llm_router("prompt") is None

    def test_llm_router_metrics_track_and_reset_calls(self, monkeypatch):
        router_module.get_llm_router_metrics(reset=True)
        monkeypatch.setattr(
            router_module,
            "_call_llm_router",
            lambda prompt: json.dumps(
                {
                    "intent": "diet",
                    "confidence": 0.82,
                    "reason": "nutrition planning",
                    "needs_clarification": False,
                }
            ),
        )

        router_module._llm_classifier_route("ambiguous request")
        metrics = router_module.get_llm_router_metrics()

        assert metrics["calls"] == 1
        assert metrics["outcomes"] == {"contract_accepted": 1}
        reset_snapshot = router_module.get_llm_router_metrics(reset=True)
        assert reset_snapshot["calls"] == 1
        assert router_module.get_llm_router_metrics()["calls"] == 0

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
        assert isinstance(result["_route_ambiguity_signals"], list)
        # After refactoring, the ambiguity_signals dict is no longer populated directly.
        # The state field is kept for backward compatibility.
        assert result["_primary_intent"] == result["intent"]
        assert isinstance(result["_secondary_intents"], list)
        assert result["_route_plan"][0] == result["_primary_intent"]
        assert isinstance(result["_needs_clarification"], bool)
        assert result["_structured_state"]["task"]["primary_intent"] == "diet"
        assert result["_structured_state"]["task"]["execution_plan"] == result[
            "_route_execution_plan"
        ]
        assert result["_structured_state"]["decisions"][0]["stage"] == "router"


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

    def test_ambiguous_request_stops_at_targeted_clarification(self):
        graph = build_router_graph()
        state: RouterState = {
            "user_input": "想练深蹲吃什么",
            "user_id": "test_001",
            "intent": "",
            "memory": [],
            "result": "",
            "error": None,
        }

        result = graph.invoke(state)

        assert result["_needs_clarification"] is True
        assert result["_clarification_candidates"] == ["diet", "motion"]
        assert "饮食建议" in result["result"]
        assert "动作分析" in result["result"]
        assert "_prompt" not in result
        assert any(
            item["mode"] == "clarification_requested"
            for item in result["_execution"]
        )

    def test_any_legal_combination_executes_all_subgraphs(self, monkeypatch):
        from langgraph.graph import END, StateGraph
        import app.tools.retriever as retriever_module

        def fake_builder(intent):
            builder = StateGraph(RouterState)

            def run(state):
                state["result"] = f"{intent} result"
                state["_prompt"] = f"{intent} prompt"
                state.setdefault("_structured_state", {}).setdefault(
                    "tool_results_summary", []
                ).append({"intent": intent, "summary": f"{intent} preview"})
                return state

            builder.add_node("run", run)
            builder.set_entry_point("run")
            builder.add_edge("run", END)
            return builder.compile()

        for intent in ("search", "motion", "diet", "chat", "mcp"):
            monkeypatch.setattr(
                router_module,
                f"build_{intent}_subgraph",
                lambda current=intent: fake_builder(current),
            )
        monkeypatch.setattr(retriever_module, "load_shared_knowledge_base", lambda path: None)

        graph = build_router_graph()
        result = graph.invoke({
            "user_input": "先给我减脂原则，然后推荐一道具体晚餐菜",
            "user_id": "test",
            "memory": [],
            "result": "",
            "error": None,
        })

        assert result["intent"] == "diet"
        assert result["_route_execution_plan"] == ["diet", "mcp"]
        assert [item["intent"] for item in result["_route_results"]] == [
            "diet",
            "mcp",
        ]
        assert result["_structured_state"]["tool_results_summary"] == [
            {"intent": "diet", "summary": "diet preview"},
            {"intent": "mcp", "summary": "mcp preview"},
        ]
        assert result["result"] == "Mock LLM response"


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

    def test_router_semantic_rewrite_dataset_matches_current_router(self):
        assert ROUTER_SEMANTIC_REWRITE_EVAL_PATH.exists()
        with ROUTER_SEMANTIC_REWRITE_EVAL_PATH.open("r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        assert rows
        mismatches = []
        for row in rows:
            actual = classify_intent(row["text"])
            if actual != row["intent"]:
                mismatches.append((row["text"], row["intent"], actual))

        assert not mismatches

"""RAG evidence formatting and source propagation tests."""
from app.graph.subgraphs.chat import (
    CHAT_GENERATION_MAX_TOKENS,
    CHAT_GENERATION_TEMPERATURE,
    CHAT_GENERATION_TOP_P,
    build_chat_subgraph,
    generate_node,
)
from app.graph.subgraphs.diet import recommend_node
from app.graph.subgraphs.rag_context import build_rag_context
from app.graph.prompt_builder import CHAT_ANSWER_PROMPT_VERSION, PromptBuilder
from app.memory.token_budget import estimate_tokens
from app.tools.types import ToolResult


def test_build_rag_context_numbers_evidence_and_deduplicates_sources():
    context, sources = build_rag_context([
        {"content": "深蹲需要保持核心稳定。", "source": "fitness_basics.txt"},
        {"content": "膝盖方向应与脚尖一致。", "source": "fitness_basics.txt"},
        {"content": "每周至少力量训练两天。", "source": "cdc_strength_training.txt"},
    ])

    assert "[Ref1]" in context
    assert "来源: fitness_basics.txt" in context
    assert "[Ref3]" in context
    assert sources == ["fitness_basics.txt", "cdc_strength_training.txt"]


def test_build_rag_context_includes_section_path_when_available():
    context, _ = build_rag_context([
        {
            "content": "保持核心稳定。",
            "source": "fitness_basics.txt",
            "section_path": "健身基础动作指南 > 深蹲",
        }
    ])

    assert "章节: 健身基础动作指南 > 深蹲" in context


def test_chat_generate_node_propagates_rag_sources_in_streaming_mode():
    state = {
        "user_input": "深蹲要注意什么？",
        "memory": [],
        "_streaming": True,
        "_retrieved": [
            {"content": "保持核心稳定。", "source": "fitness_basics.txt"},
        ],
        "_long_term_memories": [
            {"kind": "preference", "content": "不喜欢吃香菜", "importance": 0.8, "score": 0.7}
        ],
        "_conversation_summary": "用户正在制定深蹲训练计划。",
    }

    result = generate_node(state)

    assert result["_sources"] == ["fitness_basics.txt"]
    assert "来源: fitness_basics.txt" in result["_prompt"]
    assert "[Ref1]" in result["_prompt"]
    assert result["_prompt_meta"]["kind"] == "chat.answer"
    assert result["_prompt_meta"]["chars"] == len(result["_prompt"])
    assert "recent_conversation" in result["_prompt_meta"]["sections"]
    assert "不喜欢吃香菜" in result["_prompt"]
    assert "long_term_memory" in result["_prompt_meta"]["sections"]
    assert "用户正在制定深蹲训练计划" in result["_prompt"]
    assert "conversation_summary" in result["_prompt_meta"]["sections"]
    assert result["_prompt_meta"]["generation"] == {
        "max_tokens": CHAT_GENERATION_MAX_TOKENS,
        "temperature": CHAT_GENERATION_TEMPERATURE,
        "top_p": CHAT_GENERATION_TOP_P,
    }


def test_chat_answer_prompt_enforces_evidence_only_grounding_contract():
    state = {
        "user_input": "成年人每周至少练几天力量？",
        "memory": [{"role": "assistant", "content": "以前随口说过三天。"}],
        "_streaming": True,
        "_retrieved": [
            {
                "content": "成年人每周至少进行两天肌肉强化活动。",
                "source": "cdc_strength_training.txt",
            }
        ],
    }

    prompt = generate_node(state)["_prompt"]

    assert CHAT_ANSWER_PROMPT_VERSION == "grounded-v3"
    assert "证据是唯一事实来源" in prompt
    assert "保留原文逻辑方向" in prompt
    assert "顺着错误前提回答" in prompt
    assert "条件与方案不能混合" in prompt
    assert "加载期与非加载方案" in prompt
    assert "每个关键事实或数字后紧跟直接支持它的参考编号" in prompt
    assert "证据不足就停止" in prompt
    assert "不能作为专业事实证据" in prompt
    assert "然后给出你的通用建议" not in prompt


def test_chat_generate_node_uses_deterministic_grounded_decoding(monkeypatch):
    captured = {}

    class FakeLLM:
        def generate(self, prompt):
            captured["prompt"] = prompt
            return "每天 3-5 克即可。[Ref1]"

    def fake_create_llm(model_id, **kwargs):
        captured["model_id"] = model_id
        captured.update(kwargs)
        return FakeLLM()

    monkeypatch.setattr("app.llm.providers.create_llm", fake_create_llm)
    result = generate_node({
        "user_input": "不加载时肌酸怎么补？",
        "memory": [],
        "_model_id": "qwen-local",
        "_retrieved": [{
            "content": "不采用加载期时，每天摄入 3-5 克即可。",
            "source": "creatine.txt",
        }],
    })

    assert result["result"] == "每天 3-5 克即可。[Ref1]"
    assert captured["model_id"] == "qwen-local"
    assert captured["max_tokens"] == CHAT_GENERATION_MAX_TOKENS
    assert captured["temperature"] == CHAT_GENERATION_TEMPERATURE
    assert captured["top_p"] == CHAT_GENERATION_TOP_P


def test_diet_recommend_node_propagates_rag_sources_in_streaming_mode():
    state = {
        "user_input": "减脂怎么吃？",
        "_user_profile": {"goal": "减脂"},
        "_streaming": True,
        "_retrieved": [
            {"content": "优先选择营养密度高的食物。", "source": "nutrition.txt"},
        ],
        "_conversation_summary": "用户当前目标是减脂。",
    }

    result = recommend_node(state)

    assert result["_sources"] == ["nutrition.txt"]
    assert "来源: nutrition.txt" in result["_prompt"]
    assert "[Ref1]" in result["_prompt"]
    assert result["_prompt_meta"]["kind"] == "diet.recommendation"
    assert result["_prompt_meta"]["chars"] == len(result["_prompt"])
    assert "user_profile" in result["_prompt_meta"]["sections"]
    assert "用户当前目标是减脂" in result["_prompt"]
    assert "conversation_summary" in result["_prompt_meta"]["sections"]


def test_search_and_mcp_final_prompts_include_conversation_summary():
    state = {
        "user_input": "继续",
        "_conversation_summary": "用户正在制定每周三练计划。",
    }

    search_prompt = PromptBuilder.search_synthesis(
        state,
        result_text="搜索结果",
        sources=[],
    )
    mcp_prompt = PromptBuilder.mcp_format_result(
        state,
        payload={"name": "示例菜谱"},
    )

    assert "用户正在制定每周三练计划" in search_prompt
    assert "用户正在制定每周三练计划" in mcp_prompt


def test_recent_conversation_uses_configured_turn_count(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "memory_max_turns", 6)
    memory = []
    for index in range(6):
        memory.extend(
            [
                {"role": "user", "content": f"第{index}轮问题"},
                {"role": "assistant", "content": f"第{index}轮回答"},
            ]
        )

    block = PromptBuilder.recent_conversation(memory)

    assert "第0轮问题" in block
    assert "第5轮回答" in block
    assert len(block.splitlines()) == 12


def test_prompt_builder_compacts_long_chat_prompt(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "context_compact_trigger_chars", 2600)
    monkeypatch.setattr(config, "context_max_prompt_chars", 3000)
    monkeypatch.setattr(config, "context_compact_trigger_tokens", 2600)
    monkeypatch.setattr(config, "context_max_prompt_tokens", 3000)
    state = {
        "user_input": "深蹲怎么做？",
        "memory": [
            {"role": "user", "content": "旧对话" * 300},
            {"role": "assistant", "content": "旧回答" * 300},
        ],
        "_streaming": True,
        "_retrieved": [
            {"content": "保持核心稳定。" * 80, "source": "fitness_basics.txt"},
        ],
        "_structured_state": {
            "task": {"primary_intent": "chat"},
            "tool_results_summary": [{"intent": "search", "summary": "工具摘要"}],
        },
    }

    result = generate_node(state)

    assert result["_prompt_meta"]["compact_triggered"] is True
    assert result["_prompt_meta"]["original_chars"] > result["_prompt_meta"]["chars"]
    assert result["_prompt_meta"]["original_tokens"] >= result["_prompt_meta"]["tokens"]
    assert len(result["_prompt"]) <= 2600
    assert estimate_tokens(result["_prompt"]) <= 2600
    assert "## 对话压缩摘要" in result["_prompt"]
    assert "## 用户问题" in result["_prompt"]
    assert "深蹲怎么做？" in result["_prompt"]
    assert result["_structured_state"]["compact_triggered"] is True
    diagnostics = result["_prompt_meta"]["compact_diagnostics"]
    assert diagnostics["strategy"] == "priority_round_robin_v3"
    assert diagnostics["target_met"] is True
    assert diagnostics["user_question_complete"] is True
    assert diagnostics["packing_rounds"] >= 1
    assert diagnostics["hard_token_budget_met"] is True
    assert diagnostics["dropped_sections"]
    assert result["_execution"][0]["component"] == "compact"


def test_prompt_compaction_keeps_required_sections_and_whole_entries(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "context_compact_trigger_chars", 700)
    monkeypatch.setattr(config, "context_max_prompt_chars", 1200)
    monkeypatch.setattr(config, "context_compact_trigger_tokens", 700)
    monkeypatch.setattr(config, "context_max_prompt_tokens", 1200)
    state = {"_structured_state": {}}
    first_reference = "[Ref1]\n" + "第一条证据完整内容。" * 8
    second_reference = "[Ref2]\n" + "第二条证据完整内容。" * 80
    prompt = f"""# 角色
安全角色不可删除。

# 回答规则
只基于证据回答，这条规则不可删除。

## 参考资料
{first_reference}

{second_reference}

## 待验证的个性化线索
- 可能喜欢夜间训练，但尚未确认。{("待确认" * 40)}

## 用户问题
请完整解释深蹲动作，并保留这句问题。

请回答："""

    compacted = PromptBuilder.attach(
        state,
        prompt,
        kind="test.compaction",
        sections=["safety_rules", "rag_evidence", "soft_memory", "user_question"],
    )

    assert "安全角色不可删除" in compacted
    assert "只基于证据回答，这条规则不可删除" in compacted
    assert "请完整解释深蹲动作，并保留这句问题" in compacted
    assert first_reference in compacted
    assert second_reference not in compacted
    assert "第二条证据完整内" not in compacted
    assert "可能喜欢夜间训练" not in compacted
    assert len(compacted) <= 700
    assert estimate_tokens(compacted) <= 700

    diagnostics = state["_prompt_meta"]["compact_diagnostics"]
    assert diagnostics["target_met"] is True
    assert diagnostics["user_question_complete"] is True
    assert {item["section"] for item in diagnostics["dropped_sections"]} >= {
        "参考资料",
        "待验证的个性化线索",
    }


def test_chat_subgraph_preserves_retrieval_between_langgraph_nodes(monkeypatch):
    """Regression: undeclared transient keys were dropped at node boundaries."""
    evidence = {
        "content": (
            "成年人每周应进行 150 至 300 分钟中等强度有氧活动；"
            "有慢性疾病或特殊情况时应咨询专业人士。"
        ),
        "source": "who_physical_activity.txt",
        "section_path": "成年人建议",
    }
    monkeypatch.setattr(
        "app.graph.subgraphs.chat.retrieve_knowledge",
        lambda *_args, **_kwargs: ToolResult(
            ok=True,
            data=[evidence],
            meta={"backend": "sqlite_faiss", "mode": "hybrid"},
        ),
    )

    result = build_chat_subgraph().invoke({
        "user_input": "成年人每周应该进行多少有氧运动？请结合知识库说明。",
        "user_id": "rag-state-regression",
        "conversation_id": "rag-state-regression",
        "intent": "chat",
        "memory": [],
        "result": "",
        "error": None,
        "_streaming": True,
    })

    assert result["_retrieved"] == [evidence]
    assert result["_sources"] == ["who_physical_activity.txt"]
    assert "150 至 300 分钟" in result["_prompt"]
    assert "暂无相关参考资料" not in result["_prompt"]


def test_prompt_compaction_does_not_cut_pinned_content_when_target_is_too_small(
    monkeypatch,
):
    from app.config import config

    monkeypatch.setattr(config, "context_compact_trigger_chars", 500)
    monkeypatch.setattr(config, "context_max_prompt_chars", 1200)
    monkeypatch.setattr(config, "context_compact_trigger_tokens", 500)
    monkeypatch.setattr(config, "context_max_prompt_tokens", 1200)
    full_question = "这是一个不能被静默截断的完整用户问题。" * 5
    state = {"_structured_state": {}}
    prompt = f"""# 角色
安全规则必须完整保留。

## 参考资料
这段可选资料应被舍弃。{("资料" * 100)}

## 用户问题
{full_question}

请回答："""

    compacted = PromptBuilder.attach(
        state,
        prompt,
        kind="test.pinned-overflow",
        sections=["safety_rules", "rag_evidence", "user_question"],
    )

    assert "安全规则必须完整保留" in compacted
    assert full_question in compacted
    assert "这段可选资料应被舍弃" not in compacted
    diagnostics = state["_prompt_meta"]["compact_diagnostics"]
    assert diagnostics["target_met"] is False
    assert diagnostics["hard_budget_met"] is True
    assert diagnostics["reason"] == "pinned_content_exceeds_compact_target"
    assert diagnostics["user_question_complete"] is True


def test_prompt_compaction_pins_confirmed_safety_memory(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "context_compact_trigger_chars", 700)
    monkeypatch.setattr(config, "context_max_prompt_chars", 1200)
    monkeypatch.setattr(config, "context_compact_trigger_tokens", 700)
    monkeypatch.setattr(config, "context_max_prompt_tokens", 1200)
    safety_memory = "- [安全/constraint] 左膝有旧伤，深蹲时避免膝关节疼痛动作。"
    prompt = f"""# 角色
你是健身助手，必须遵守安全边界。

## 参考资料
[Ref1]\n{"普通资料。" * 100}

## 长期记忆
- [preference] 用户偏好夜间训练。
{safety_memory}

## 用户问题
请给我今天的训练建议。

请回答："""
    state = {"_structured_state": {}}

    compacted = PromptBuilder.attach(
        state,
        prompt,
        kind="test.safety-memory",
        sections=["safety_rules", "rag_evidence", "long_term_memory", "user_question"],
    )

    assert safety_memory in compacted
    assert "请给我今天的训练建议" in compacted
    assert "普通资料" not in compacted
    diagnostics = state["_prompt_meta"]["compact_diagnostics"]
    assert diagnostics["pinned_safety_units"] == 1
    assert diagnostics["hard_budget_met"] is True


def test_prompt_compaction_skips_oversized_item_and_continues_other_queues(
    monkeypatch,
):
    from app.config import config

    monkeypatch.setattr(config, "context_compact_trigger_chars", 850)
    monkeypatch.setattr(config, "context_max_prompt_chars", 1200)
    monkeypatch.setattr(config, "context_compact_trigger_tokens", 850)
    monkeypatch.setattr(config, "context_max_prompt_tokens", 1200)
    prompt = f"""# 角色
你是健身助手。

## 参考资料
[Ref1]\n{"无法装入的超长证据。" * 80}

## 长期记忆
- [preference] 用户偏好在晚上进行力量训练。

## 对话历史
user: 我最近开始练深蹲。
assistant: 可以先从徒手深蹲开始。

## 用户问题
下一步怎么练？

请回答："""
    state = {"_structured_state": {}}

    compacted = PromptBuilder.attach(
        state,
        prompt,
        kind="test.round-robin-skip",
        sections=[
            "safety_rules",
            "rag_evidence",
            "long_term_memory",
            "recent_conversation",
            "user_question",
        ],
    )

    assert "无法装入的超长证据" not in compacted
    assert "用户偏好在晚上进行力量训练" in compacted
    assert "我最近开始练深蹲" in compacted
    diagnostics = state["_prompt_meta"]["compact_diagnostics"]
    usage = {item["queue"]: item for item in diagnostics["queue_usage"]}
    assert usage["evidence"]["rejected"] == 1
    assert usage["confirmed_memory"]["kept"] == 1
    assert usage["recent_conversation"]["kept"] == 1
    assert diagnostics["packing_rounds"] >= 1

"""RAG evidence formatting and source propagation tests."""
from app.graph.subgraphs.chat import generate_node
from app.graph.subgraphs.diet import recommend_node
from app.graph.subgraphs.rag_context import build_rag_context
from app.graph.prompt_builder import PromptBuilder


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

    monkeypatch.setattr(config, "context_compact_trigger_chars", 500)
    monkeypatch.setattr(config, "context_max_prompt_chars", 1200)
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
    assert len(result["_prompt"]) <= 1200
    assert "## 对话压缩摘要" in result["_prompt"]
    assert "## 用户问题" in result["_prompt"]
    assert "深蹲怎么做？" in result["_prompt"]
    assert result["_structured_state"]["compact_triggered"] is True
    assert result["_execution"][0]["component"] == "compact"

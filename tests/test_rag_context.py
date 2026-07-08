"""RAG evidence formatting and source propagation tests."""
from app.graph.subgraphs.chat import generate_node
from app.graph.subgraphs.diet import recommend_node
from app.graph.subgraphs.rag_context import build_rag_context


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


def test_chat_generate_node_propagates_rag_sources_in_streaming_mode():
    state = {
        "user_input": "深蹲要注意什么？",
        "memory": [],
        "_streaming": True,
        "_retrieved": [
            {"content": "保持核心稳定。", "source": "fitness_basics.txt"},
        ],
    }

    result = generate_node(state)

    assert result["_sources"] == ["fitness_basics.txt"]
    assert "来源: fitness_basics.txt" in result["_prompt"]
    assert "[Ref1]" in result["_prompt"]


def test_diet_recommend_node_propagates_rag_sources_in_streaming_mode():
    state = {
        "user_input": "减脂怎么吃？",
        "_user_profile": '{"goal":"减脂"}',
        "_streaming": True,
        "_retrieved": [
            {"content": "优先选择营养密度高的食物。", "source": "nutrition.txt"},
        ],
    }

    result = recommend_node(state)

    assert result["_sources"] == ["nutrition.txt"]
    assert "来源: nutrition.txt" in result["_prompt"]
    assert "[Ref1]" in result["_prompt"]

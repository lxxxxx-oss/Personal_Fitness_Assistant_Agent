"""Knowledge/RAG registry integration tests."""

from app.tools.registry import ToolRegistry, ToolSpec
from app.tools.types import ErrorCode, ToolResult


def _knowledge_registry(result: ToolResult, captured_args=None) -> ToolRegistry:
    def execute(args):
        if captured_args is not None:
            captured_args.append(args)
        return result

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="knowledge.retrieve",
            description="Fake knowledge retriever.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "top_k": {"type": "integer", "minimum": 1},
                    "threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
            },
            permission="read_knowledge",
            executor=execute,
        )
    )
    return registry


def test_chat_retrieve_node_uses_registry(monkeypatch):
    from app.graph.subgraphs import rag_context
    from app.graph.subgraphs.chat import retrieve_node

    tool_result = ToolResult.ok(
        data=[{"content": "深蹲需要保持核心稳定", "source": "kb/squat.md"}],
        backend="memory",
        mode="embedding",
    )
    registry = _knowledge_registry(tool_result)
    monkeypatch.setattr(rag_context, "_rag_tool_registry", registry)
    state = {
        "user_input": "深蹲怎么做",
        "user_id": "u1",
        "intent": "chat",
        "memory": [],
        "result": "",
        "error": None,
    }

    result_state = retrieve_node(state)

    assert result_state["_retrieved"] == tool_result.data
    assert result_state["_retrieval_meta"]["tool_name"] == "knowledge.retrieve"
    assert result_state["_retrieval_meta"]["execution_id"]
    assert result_state["_execution"] == [
        {
            "component": "rag",
            "mode": "memory_embedding",
            "degraded": False,
        }
    ]
    assert registry.audit_log[-1]["tool_name"] == "knowledge.retrieve"


def test_diet_retrieve_node_uses_registry(monkeypatch):
    from app.graph.subgraphs import rag_context
    from app.graph.subgraphs.diet import retrieve_nutrition_node

    tool_result = ToolResult.ok(
        data=[{"content": "减脂期需要控制总热量", "source": "kb/diet.md"}],
        backend="memory",
        mode="embedding",
    )
    monkeypatch.setattr(rag_context, "_rag_tool_registry", _knowledge_registry(tool_result))
    state = {
        "user_input": "我想减脂怎么吃",
        "user_id": "u1",
        "intent": "diet",
        "memory": [],
        "result": "",
        "error": None,
        "_user_profile": {"goal": "减脂"},
    }

    result_state = retrieve_nutrition_node(state)

    assert result_state["_retrieved"] == tool_result.data
    assert result_state["_retrieval_meta"]["tool_name"] == "knowledge.retrieve"
    assert result_state["_execution"][0]["component"] == "rag"


def test_retrieve_nodes_use_configured_rag_parameters(monkeypatch):
    from app.config import config
    from app.graph.subgraphs import rag_context
    from app.graph.subgraphs.chat import retrieve_node
    from app.graph.subgraphs.diet import retrieve_nutrition_node

    captured_args = []
    monkeypatch.setattr(config, "retriever_top_k", 3)
    monkeypatch.setattr(config, "retriever_threshold", 0.72)
    monkeypatch.setattr(
        rag_context,
        "_rag_tool_registry",
        _knowledge_registry(
            ToolResult.ok(data=[], backend="memory", mode="embedding"),
            captured_args=captured_args,
        ),
    )
    state = {
        "user_input": "深蹲怎么做",
        "user_id": "u1",
        "intent": "chat",
        "memory": [],
        "result": "",
        "error": None,
    }

    retrieve_node(state)
    diet_state = {
        "user_input": "减脂怎么吃",
        "user_id": "u1",
        "intent": "diet",
        "memory": [],
        "result": "",
        "error": None,
        "_user_profile": {"goal": "减脂"},
    }
    retrieve_nutrition_node(diet_state)

    assert captured_args[0]["top_k"] == 3
    assert captured_args[0]["threshold"] == 0.72
    assert captured_args[1]["top_k"] == 3
    assert captured_args[1]["threshold"] == 0.72


def test_chat_retrieve_node_records_registry_failure(monkeypatch):
    from app.graph.subgraphs import rag_context
    from app.graph.subgraphs.chat import retrieve_node

    tool_result = ToolResult.fail(ErrorCode.NETWORK_ERROR, "retriever unavailable")
    monkeypatch.setattr(rag_context, "_rag_tool_registry", _knowledge_registry(tool_result))
    state = {
        "user_input": "深蹲怎么做",
        "user_id": "u1",
        "intent": "chat",
        "memory": [],
        "result": "",
        "error": None,
    }

    result_state = retrieve_node(state)

    assert result_state["_retrieved"] == []
    assert result_state["_retrieval_meta"]["tool_name"] == "knowledge.retrieve"
    assert result_state["_execution"] == [
        {
            "component": "rag",
            "mode": "memory",
            "degraded": True,
            "detail": "Retrieval failed",
        }
    ]

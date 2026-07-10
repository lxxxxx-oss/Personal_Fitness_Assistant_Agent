"""Search tool tests."""
from app.tools.registry import ToolRegistry, ToolSpec
from app.tools.search_tool import TavilySearchTool
from app.tools.types import ToolResult


class TestTavilySearchTool:
    def test_mock_search_without_api_key(self):
        tool = TavilySearchTool(api_key="")
        result = tool.search("squat standard form", max_results=3)
        assert result.ok
        assert len(result.data) >= 1
        assert "title" in result.data[0]
        assert "content" in result.data[0]
        assert "url" in result.data[0]
        assert result.meta["is_mock"] is True

    def test_mock_search_respects_max_results(self):
        tool = TavilySearchTool(api_key="")
        result = tool.search("fitness", max_results=1)
        assert result.ok
        assert len(result.data) == 1

    def test_invalid_query_returns_error(self):
        tool = TavilySearchTool(api_key="")
        result = tool.search("", max_results=3)
        assert not result.ok
        assert result.error_code == "INVALID_PARAM"

    def test_query_too_long_returns_error(self):
        tool = TavilySearchTool(api_key="")
        result = tool.search("x" * 501, max_results=3)
        assert not result.ok
        assert result.error_code == "INVALID_PARAM"

    def test_max_results_out_of_range(self):
        tool = TavilySearchTool(api_key="")
        result = tool.search("fitness", max_results=999)
        assert not result.ok
        assert result.error_code == "INVALID_PARAM"

    def test_search_subgraph_records_mock_execution(self, monkeypatch):
        from app.graph.subgraphs import search as search_subgraph

        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="search.tavily",
                description="Search through mock Tavily.",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1},
                        "max_results": {"type": "integer", "minimum": 1},
                    },
                },
                permission="network",
                executor=lambda args: TavilySearchTool(api_key="").search(
                    args["query"], args.get("max_results", 5)
                ),
            )
        )
        monkeypatch.setattr(search_subgraph, "_tool_registry", registry)
        state = {
            "user_input": "最新深蹲研究",
            "user_id": "u1",
            "intent": "search",
            "memory": [],
            "result": "",
            "error": None,
            "_search_query": "深蹲 研究",
        }

        result_state = search_subgraph.search_node(state)

        assert result_state["_search_meta"]["tool_name"] == "search.tavily"
        assert result_state["_search_meta"]["permission"] == "network"
        assert result_state["_structured_state"]["tool_results_summary"][0][
            "tool"
        ] == "search.tavily"
        assert result_state["_structured_state"]["tool_results_summary"][0][
            "data_ref"
        ] == "_search_results"
        assert result_state["_execution"] == [
            {
                "component": "search",
                "mode": "mock",
                "degraded": True,
                "detail": "Tavily API key not configured; using demo search data",
            }
        ]

    def test_search_subgraph_records_registry_failure(self, monkeypatch):
        from app.graph.subgraphs import search as search_subgraph

        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="search.tavily",
                description="Failing search tool.",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1},
                        "max_results": {"type": "integer", "minimum": 1},
                    },
                },
                permission="network",
                executor=lambda args: ToolResult.fail(
                    "NETWORK_ERROR", "search unavailable"
                ),
            )
        )
        monkeypatch.setattr(search_subgraph, "_tool_registry", registry)
        state = {
            "user_input": "最新深蹲研究",
            "user_id": "u1",
            "intent": "search",
            "memory": [],
            "result": "",
            "error": None,
            "_search_query": "深蹲 研究",
        }

        result_state = search_subgraph.search_node(state)

        assert result_state["_search_results"] == []
        assert "search_degraded:NETWORK_ERROR" in result_state[
            "_route_execution_warnings"
        ]
        assert result_state["_execution"] == [
            {
                "component": "search",
                "mode": "tavily",
                "degraded": True,
                "detail": "Tavily request failed",
            }
        ]

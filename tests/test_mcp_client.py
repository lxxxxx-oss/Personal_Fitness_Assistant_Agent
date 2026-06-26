"""MCP client tests — real howtocook-mcp tool names and MCP content format."""
from app.tools.mcp_client import MCPClient


class TestMCPClient:
    def test_client_initial_state(self):
        client = MCPClient(server_command="echo")
        assert not client.is_connected
        assert client.server_command == "echo"

    def test_client_disconnect_when_not_connected(self):
        client = MCPClient(server_command="echo")
        result = client.disconnect()
        assert result.ok
        assert not client.is_connected

    def test_format_jsonrpc_request(self):
        client = MCPClient(server_command="echo")
        req = client._build_request("tools/list", {})
        assert req["jsonrpc"] == "2.0"
        assert "id" in req
        assert req["method"] == "tools/list"


class TestMCPMockMode:
    """Test mock mode with real howtocook-mcp tool names."""

    def test_mock_list_tools(self):
        client = MCPClient(server_command="mock")
        result = client.list_tools()
        assert result.ok
        assert isinstance(result.data, list)
        assert len(result.data) == 5
        tool_names = [t["name"] for t in result.data]
        assert "mcp_howtocook_getRecipeById" in tool_names
        assert "mcp_howtocook_getRecipesByCategory" in tool_names
        assert "mcp_howtocook_whatToEat" in tool_names
        assert "mcp_howtocook_recommendMeals" in tool_names
        assert "mcp_howtocook_getAllRecipes" in tool_names

    def test_mock_get_recipe_by_id_found(self):
        client = MCPClient(server_command="mock")
        result = client.call_tool(
            "mcp_howtocook_getRecipeById",
            {"query": "番茄炒蛋"},
        )
        assert result.ok
        assert "name" in result.data
        assert result.data["name"] == "番茄炒蛋"
        assert "ingredients" in result.data
        assert "steps" in result.data

    def test_mock_get_recipe_by_id_not_found(self):
        client = MCPClient(server_command="mock")
        result = client.call_tool(
            "mcp_howtocook_getRecipeById",
            {"query": "佛跳墙"},
        )
        assert result.ok
        # Data contains an error field at application level — tool call itself succeeded
        assert "error" in result.data
        assert "未找到" in result.data.get("error", "")

    def test_mock_get_recipes_by_category(self):
        client = MCPClient(server_command="mock")
        result = client.call_tool(
            "mcp_howtocook_getRecipesByCategory",
            {"category": "荤菜"},
        )
        assert result.ok
        assert isinstance(result.data, list)
        assert len(result.data) >= 1
        assert "name" in result.data[0]

    def test_mock_what_to_eat(self):
        client = MCPClient(server_command="mock")
        result = client.call_tool(
            "mcp_howtocook_whatToEat",
            {"peopleCount": 3},
        )
        assert result.ok
        assert "recommendations" in result.data
        assert result.data["peopleCount"] == 3

    def test_mock_recommend_meals(self):
        client = MCPClient(server_command="mock")
        result = client.call_tool(
            "mcp_howtocook_recommendMeals",
            {
                "peopleCount": 2,
                "allergies": ["虾"],
                "avoidItems": ["葱"],
            },
        )
        assert result.ok
        assert "weeklyPlan" in result.data
        assert "shoppingList" in result.data

    def test_mock_get_all_recipes(self):
        client = MCPClient(server_command="mock")
        result = client.call_tool(
            "mcp_howtocook_getAllRecipes",
            {},
        )
        assert result.ok
        assert isinstance(result.data, list)
        assert len(result.data) >= 1

    def test_mock_unknown_tool(self):
        client = MCPClient(server_command="mock")
        result = client.call_tool("nonexistent_tool", {})
        assert result.ok
        # Unknown tool returns error at application level in data
        assert "error" in result.data

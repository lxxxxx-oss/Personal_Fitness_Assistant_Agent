"""Search tool tests."""
from app.tools.search_tool import TavilySearchTool


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

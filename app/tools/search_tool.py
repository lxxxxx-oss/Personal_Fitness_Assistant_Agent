"""Tavily search tool wrapper — standardized with ToolResult."""

# PERMISSION: This tool is for fitness/health information search only.
# It must NOT be used for: medical diagnosis, illegal content,
# harassment, or any query outside the fitness domain.
# If a search query appears to request medical advice, the caller
# should redirect to a qualified healthcare professional.

import logging
from typing import Dict, List

from app.tools.types import (
    ToolResult,
    ErrorCode,
    check_str_nonempty,
    check_str_len,
    check_int_range,
)

logger = logging.getLogger(__name__)

# --- Constants ---
MAX_QUERY_LENGTH = 500
MIN_RESULTS = 1
MAX_RESULTS = 20


class TavilySearchTool:
    """Wraps the Tavily Search API with structured error handling.

    Input:
        query:      str, 1-500 chars
        max_results: int, 1-20

    Output:
        ToolResult.data = [{"title": str, "url": str, "content": str}, ...]
        ToolResult.meta = {"is_mock": bool, "api_key_configured": bool}
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5) -> ToolResult:
        """Execute search and return ToolResult.

        Raises nothing — all errors are captured in ToolResult.
        """
        # --- Input validation ---
        err = check_str_nonempty(query, "query")
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        err = check_str_len(query, "query", max_len=MAX_QUERY_LENGTH)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        err = check_int_range(max_results, "max_results", MIN_RESULTS, MAX_RESULTS)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)

        # --- Permission gate ---
        blocked = _check_blocked_query(query)
        if blocked:
            return ToolResult.fail(
                ErrorCode.PERMISSION_DENIED,
                f"Query blocked: {blocked}",
                meta={"query": query, "reason": blocked},
            )

        # --- Config check ---
        if not self.api_key:
            logger.warning("TAVILY_API_KEY not set, using mock search")
            return ToolResult.ok(
                data=self._mock_search(query, max_results),
                is_mock=True,
                api_key_configured=False,
            )

        # --- Real search ---
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=self.api_key)
            response = client.search(query=query, max_results=max_results)
            results = []
            for r in response.get("results", [])[:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                })

            if not results:
                return ToolResult.ok(
                    data=results,
                    is_mock=False,
                    api_key_configured=True,
                    note="Search completed but returned no results",
                )

            return ToolResult.ok(
                data=results,
                is_mock=False,
                api_key_configured=True,
            )

        except Exception as e:
            error_msg = str(e)
            if any(kw in error_msg.lower() for kw in
                   ["timeout", "connection", "refused", "unreachable", "dns"]):
                code = ErrorCode.NETWORK_ERROR
                detail = f"Tavily API unreachable: {error_msg}"
            elif any(kw in error_msg.lower() for kw in
                     ["unauthorized", "forbidden", "invalid api key", "auth"]):
                code = ErrorCode.PERMISSION_DENIED
                detail = f"Tavily API auth failed: {error_msg}"
            else:
                code = ErrorCode.INTERNAL_ERROR
                detail = f"Tavily search failed: {error_msg}"

            logger.error(detail)
            return ToolResult.fail(
                code,
                detail,
                meta={"fallback": "mock_search"},
            )

    def _mock_search(self, query: str, max_results: int) -> List[Dict[str, str]]:
        """Return placeholder results when API key is not configured."""
        return [
            {
                "title": f"Search result: {query}",
                "url": "https://example.com/mock",
                "content": (
                    f"Mock search result for '{query}'. "
                    f"Configure TAVILY_API_KEY environment variable for real results."
                ),
            }
        ]


def _check_blocked_query(query: str) -> str:
    """Check if a query falls into blocked categories.

    Returns an error reason string if blocked, empty string if allowed.
    """
    q = query.lower()
    blocked_patterns = [
        ("how to hack", "security bypass"),
        ("illegal", "illegal content"),
        ("self-harm", "self-harm"),
        ("suicide", "self-harm"),
        ("prescribe", "medical prescription"),
        ("diagnose", "medical diagnosis"),
    ]
    for pattern, category in blocked_patterns:
        if pattern in q:
            return f"Query matches blocked pattern: {category}"
    return ""

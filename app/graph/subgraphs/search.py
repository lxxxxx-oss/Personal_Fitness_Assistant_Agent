"""Search subgraph — Tavily web search three-stage pipeline."""
import logging

from langgraph.graph import StateGraph, END

from app.graph.prompt_builder import PromptBuilder
from app.graph.state import RouterState, record_execution
from app.graph.structured_state import add_tool_preview, truncate_text
from app.tools.registry import ToolRegistry, build_default_tool_registry

logger = logging.getLogger(__name__)

_tool_registry: ToolRegistry = None


def _get_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = build_default_tool_registry()
    return _tool_registry


def query_understanding_node(state: RouterState) -> RouterState:
    """Query Understanding: LLM rewrites query into optimized search keywords."""
    from app.config import config
    from app.llm.loader import LLMLoader

    user_input = state["user_input"]
    prompt = PromptBuilder.search_query_rewrite(user_input)

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=64,
        temperature=0.3,
    )
    rewritten = llm.generate(prompt).strip()
    if not rewritten:
        rewritten = user_input
    state["_search_query"] = rewritten  # type: ignore
    logger.info(f"Query rewritten: '{user_input}' -> '{rewritten}'")
    return state


def search_node(state: RouterState) -> RouterState:
    """Tavily Search: execute web search."""
    query = state.get("_search_query", state["user_input"])  # type: ignore
    registry = _get_registry()
    result = registry.execute(
        "search.tavily",
        {"query": query, "max_results": 5},
        context={"allowed_permissions": ["network"]},
    )
    search_results = result.data if result.ok and result.data else []
    state["_search_results"] = search_results  # type: ignore
    state["_search_meta"] = result.meta  # type: ignore
    if search_results:
        summary = "\n".join(
            f"[{index + 1}] {item.get('title', '')}: "
            f"{truncate_text(item.get('content', ''), 180)}"
            for index, item in enumerate(search_results[:3])
        )
        add_tool_preview(
            state,
            intent="search",
            tool="search.tavily",
            summary=summary,
            data_ref="_search_results",
        )
    is_mock = bool(result.meta.get("is_mock"))
    record_execution(
        state,
        "search",
        "mock" if is_mock else "tavily",
        degraded=is_mock or not result.ok,
        detail=(
            "Tavily API key not configured; using demo search data"
            if is_mock
            else ("Tavily request failed" if not result.ok else "")
        ),
    )
    if not result.ok:
        state["_route_execution_warnings"] = state.get(
            "_route_execution_warnings", []
        ) + [f"search_degraded:{result.error_code or 'unknown'}"]
    logger.info(f"Search returned {len(search_results)} results for: {query}")
    return state


def synthesis_node(state: RouterState) -> RouterState:
    """Answer Synthesis: LLM generates structured answer from search results."""
    from app.config import config
    from app.llm.loader import LLMLoader

    results = state.get("_search_results", [])  # type: ignore
    sources = []
    result_text = ""
    for i, r in enumerate(results):
        result_text += (
            f"\n[{i+1}] {r['title']}\n"
            f"{truncate_text(r['content'], 600)}\n"
            f"Source: {r['url']}\n"
        )
        sources.append(r["url"])

    prompt = PromptBuilder.search_synthesis(
        state,
        result_text=result_text,
        sources=sources,
    )
    if state.get("_streaming"):
        state["result"] = ""
        state["_sources"] = sources  # type: ignore
        return state

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    state["_sources"] = sources  # type: ignore
    return state


def build_search_subgraph():
    """Build Search subgraph: query_understanding -> search -> synthesis -> END."""
    builder = StateGraph(RouterState)
    builder.add_node("query_understanding", query_understanding_node)
    builder.add_node("search", search_node)
    builder.add_node("synthesis", synthesis_node)
    builder.set_entry_point("query_understanding")
    builder.add_edge("query_understanding", "search")
    builder.add_edge("search", "synthesis")
    builder.add_edge("synthesis", END)
    return builder.compile()

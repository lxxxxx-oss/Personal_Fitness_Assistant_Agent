"""Search subgraph — Tavily web search three-stage pipeline."""
import logging

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState, record_execution
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
    prompt = f"""# 任务
将用户问题改写为 1-2 个简洁的搜索关键词（用空格分隔），用于搜索引擎检索健身相关信息。

# 规则
- 提取核心概念，去掉口语化的问句结构
- 中英文关键词均可，优先中文
- 只输出关键词本身，不要任何解释或标点

# 示例
用户问题: "深蹲的时候膝盖总响是怎么回事"
输出: 深蹲 膝盖弹响 原因

用户问题: "减脂期间能不能吃水果，什么时候吃最好"
输出: 减脂 水果摄入 时机

用户问题: {user_input}
输出:"""

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
        result_text += f"\n[{i+1}] {r['title']}\n{r['content']}\nSource: {r['url']}\n"
        sources.append(r["url"])

    prompt = f"""# 角色
你是一个专业的健身知识助手，现在需要基于联网搜索结果回答用户问题。

# 回答规则
1. **摘要先行**：先用 1-2 句话概括核心答案。
2. **要点展开**：列出 2-4 个关键要点，每个用 1-2 句话说明。
3. **来源标注**：引用的信息后标注来源编号（如 [来源1]）。
4. **诚实说明**：如果搜索结果与用户问题不相关或不充分，直接说明"搜索结果中未找到相关信息"，然后给出你的通用健身建议。
5. **安全提醒**：涉及伤病、药物等问题时，引导用户咨询专业医生。

# 搜索结果
{result_text or "暂无搜索结果"}

# 用户问题
{state['user_input']}

请回答："""

    state["_prompt"] = prompt  # type: ignore
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

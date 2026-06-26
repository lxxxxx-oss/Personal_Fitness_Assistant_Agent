"""MCPTool subgraph — MCP protocol tool invocation."""
import json
import logging

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState
from app.tools.mcp_client import MCPClient

logger = logging.getLogger(__name__)

_mcp_client: MCPClient = None


def _get_client() -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        from app.config import config

        _mcp_client = MCPClient(server_command=config.mcp_server_command)
        _mcp_client.connect()
    return _mcp_client


def discover_tools_node(state: RouterState) -> RouterState:
    """Discover available MCP tools."""
    client = _get_client()
    result = client.list_tools()
    state["_mcp_tools"] = result.data if result.ok else []  # type: ignore
    logger.info(f"MCP tools available: {[t['name'] for t in (result.data or [])]}")
    return state


def plan_tool_call_node(state: RouterState) -> RouterState:
    """LLM decides which MCP tool to call and with what parameters."""
    from app.config import config
    from app.llm.loader import LLMLoader

    tools = state.get("_mcp_tools", [])  # type: ignore
    tools_desc = "\n".join(
        [f"- {t['name']}: {t.get('description', '')}" for t in tools]
    )

    prompt = f"""# 角色
你是一个厨房助手，帮助用户查询菜谱和食材。

# 任务
根据用户问题，从可用工具中选择最合适的一个，提取所需参数。只输出 JSON，不要其他内容。

# 可用工具
{tools_desc}

# 工具选择指南
- 用户想查某个具体菜谱 → 用 mcp_howtocook_getRecipeById，参数 query
- 用户按分类浏览菜谱（如"荤菜""素菜""汤"）→ 用 mcp_howtocook_getRecipesByCategory，参数 category
- 用户不知道吃什么 → 用 mcp_howtocook_whatToEat，参数 peopleCount
- 用户需要一周膳食计划/智能推荐 → 用 mcp_howtocook_recommendMeals，参数 peopleCount + allergies + avoidItems
- 用户想看所有菜谱 → 用 mcp_howtocook_getAllRecipes

# 示例
用户: "番茄炒蛋怎么做"
输出: {{"tool": "mcp_howtocook_getRecipeById", "arguments": {{"query": "番茄炒蛋"}}}}

用户: "有什么荤菜推荐"
输出: {{"tool": "mcp_howtocook_getRecipesByCategory", "arguments": {{"category": "荤菜"}}}}

用户: "两个人吃，不知道吃什么"
输出: {{"tool": "mcp_howtocook_whatToEat", "arguments": {{"peopleCount": 2}}}}

用户: "帮我做一周膳食计划，3个人，忌葱姜，虾过敏"
输出: {{"tool": "mcp_howtocook_recommendMeals", "arguments": {{"peopleCount": 3, "allergies": ["虾"], "avoidItems": ["葱", "姜"]}}}}

# 用户问题
{state['user_input']}

输出 JSON:"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=256,
        temperature=0.2,
    )
    plan_text = llm.generate(prompt)
    state["_tool_plan"] = plan_text  # type: ignore
    return state


def execute_tool_node(state: RouterState) -> RouterState:
    """Execute MCP tool call."""
    client = _get_client()
    plan_text = state.get("_tool_plan", "{}")  # type: ignore

    try:
        if "{" in plan_text and "}" in plan_text:
            start = plan_text.index("{")
            end = plan_text.rindex("}") + 1
            plan_json = json.loads(plan_text[start:end])
        else:
            plan_json = {}
        tool_name = plan_json.get("tool", "mcp_howtocook_getRecipeById")
        arguments = plan_json.get("arguments", {"query": state["user_input"]})
    except (json.JSONDecodeError, ValueError):
        tool_name = "mcp_howtocook_getRecipeById"
        arguments = {"query": state["user_input"]}

    result = client.call_tool(tool_name, arguments)
    state["_tool_result"] = result  # type: ignore
    return state


def format_result_node(state: RouterState) -> RouterState:
    """Format MCP tool result into user-friendly reply."""
    from app.config import config
    from app.llm.loader import LLMLoader

    tool_result = state.get("_tool_result")  # type: ignore

    # Extract data from ToolResult wrapper; fall back to string or empty dict.
    if hasattr(tool_result, 'data'):
        if tool_result.ok:
            payload = tool_result.data
        else:
            payload = f"查询失败: {tool_result.error_message or '未知错误'}"
    else:
        payload = tool_result or {}

    prompt = f"""# 任务
将菜谱查询结果格式化为清晰易读的回复。

# 格式要求
- 菜名作为标题
- 配料清单用列表
- 步骤用编号
- 末尾可附小贴士和热量信息（如果有）
- 语言亲切但不过度啰嗦
- 如果数据中包含error字段，如实告知用户并给出建议

# 工具返回数据
{json.dumps(payload, ensure_ascii=False, indent=2) if not isinstance(payload, str) else payload}

# 用户问题
{state['user_input']}

请格式化回复："""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
    )
    state["_prompt"] = prompt  # type: ignore
    answer = llm.generate(prompt)
    state["result"] = answer
    return state


def build_mcp_subgraph():
    """Build MCPTool subgraph: discover -> plan -> execute -> format -> END."""
    builder = StateGraph(RouterState)
    builder.add_node("discover", discover_tools_node)
    builder.add_node("plan", plan_tool_call_node)
    builder.add_node("execute", execute_tool_node)
    builder.add_node("format", format_result_node)
    builder.set_entry_point("discover")
    builder.add_edge("discover", "plan")
    builder.add_edge("plan", "execute")
    builder.add_edge("execute", "format")
    builder.add_edge("format", END)
    return builder.compile()

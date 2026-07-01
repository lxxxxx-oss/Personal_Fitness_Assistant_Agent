"""Diet subgraph — RAG-enhanced personalized diet recommendations."""
import logging

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState
from app.tools.retriever import get_shared_retriever

logger = logging.getLogger(__name__)


def extract_profile_node(state: RouterState) -> RouterState:
    """Extract user body parameters and goals."""
    from app.config import config
    from app.llm.loader import LLMLoader

    prompt = f"""# 任务
从用户输入中提取个人身体参数和健身目标。缺失的字段标为"未知"。

# 提取字段
- height_cm: 身高(厘米)
- weight_kg: 体重(公斤)
- gender: 性别 (男/女/未知)
- goal: 目标 (减脂/增肌/保持/未知)
- preferences: 饮食偏好 (如不吃猪肉、素食等，没有则写"无")

# 格式要求
只输出 JSON，不要任何解释文字。

# 示例
用户输入: "我身高170体重80公斤，男性，想减脂"
输出: {{"height_cm": 170, "weight_kg": 80, "gender": "男", "goal": "减脂", "preferences": "无"}}

用户输入: "我是素食者，想增肌但不知道吃什么"
输出: {{"height_cm": "未知", "weight_kg": "未知", "gender": "未知", "goal": "增肌", "preferences": "素食"}}

用户输入: {state['user_input']}
输出:"""

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=256,
        temperature=0.2,
    )
    profile_text = llm.generate(prompt)
    state["_user_profile"] = profile_text  # type: ignore
    return state


def retrieve_nutrition_node(state: RouterState) -> RouterState:
    """RAG retrieval: search shared nutrition knowledge base."""
    from app.config import config

    retriever = get_shared_retriever()
    query = f"{state['user_input']} {state.get('_user_profile', '')}"
    result = retriever.search(
        query,
        top_k=config.retriever_top_k,
        threshold=config.retriever_threshold,
    )
    state["_retrieved"] = result.data if result.ok else []  # type: ignore
    return state


def recommend_node(state: RouterState) -> RouterState:
    """Generate personalized diet recommendations."""
    from app.config import config
    from app.llm.loader import LLMLoader

    profile = state.get("_user_profile", "")
    retrieved = state.get("_retrieved", [])  # type: ignore
    context_text = "\n".join(
        [
            f"[来源: {r.get('source', 'unknown')}] {r['content']}"
            for r in retrieved
        ]
    ) if retrieved else ""

    prompt = f"""# 角色
你是一位注册运动营养师，专长于减脂饮食规划和增肌营养方案。

# 回答规则
1. **先评估用户画像**：如果身高、体重、目标缺失较多，先引导用户补充基本信息，再给通用建议。
2. **结构化输出**：
   - 用户画像摘要（已知信息整理）
   - 核心建议（与目标直接相关的1-3条原则性建议）
   - 具体食物推荐（标注大致份量）
   - 参考餐次安排（早/中/晚/加餐示例）
   - 注意事项（过敏、禁忌等）
3. **数据来源**：如果使用了参考资料中的信息，在相关处标注。
4. **安全提醒**：不推荐极端饮食（如极低热量、单一食物减肥法）。有基础疾病的用户建议咨询医生。

# 用户画像
{profile or "用户未提供个人信息"}

# 营养知识参考
{context_text or "暂无参考资料"}

# 用户问题
{state['user_input']}

请提供饮食建议："""

    state["_prompt"] = prompt  # type: ignore
    if state.get("_streaming"):
        state["result"] = ""
        return state

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    return state


def build_diet_subgraph():
    """Build Diet subgraph: extract_profile -> retrieve -> recommend -> END."""
    builder = StateGraph(RouterState)
    builder.add_node("extract_profile", extract_profile_node)
    builder.add_node("retrieve_nutrition", retrieve_nutrition_node)
    builder.add_node("recommend", recommend_node)
    builder.set_entry_point("extract_profile")
    builder.add_edge("extract_profile", "retrieve_nutrition")
    builder.add_edge("retrieve_nutrition", "recommend")
    builder.add_edge("recommend", END)
    return builder.compile()

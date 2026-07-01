"""Chat subgraph — RAG knowledge Q&A."""
import logging

from langgraph.graph import StateGraph, END

from app.graph.state import RouterState
from app.tools.retriever import get_shared_retriever

logger = logging.getLogger(__name__)


def retrieve_node(state: RouterState) -> RouterState:
    """Retrieve relevant documents from the shared knowledge base."""
    from app.config import config

    retriever = get_shared_retriever()
    result = retriever.search(
        state["user_input"],
        top_k=config.retriever_top_k,
        threshold=config.retriever_threshold,
    )
    state["_retrieved"] = result.data if result.ok else []  # type: ignore
    state["_retrieval_meta"] = result.meta  # type: ignore
    logger.info(f"Retrieved {len(result.data)} chunks for: {state['user_input'][:50]}")
    return state


def generate_node(state: RouterState) -> RouterState:
    """Generate answer based on retrieved context + memory + user input."""
    from app.llm.loader import LLMLoader
    from app.config import config

    retrieved = state.get("_retrieved", [])  # type: ignore
    context_text = ""
    sources = []
    if retrieved:
        for i, r in enumerate(retrieved):
            source = f" 来源: {r.get('source')}" if r.get("source") else ""
            context_text += f"\n[Ref{i+1}{source}] {r['content']}"
            sources.append(r["content"][:80] + "...")

    memory = state.get("memory", [])
    memory_text = ""
    if memory:
        recent = memory[-6:]
        memory_text = "\n".join(
            [f"{m['role']}: {m['content']}" for m in recent]
        )

    prompt = f"""# 角色
你是一个专业的健身知识助手，由运动科学和力量训练领域的知识库支持。你的专长包括：
- 力量训练动作讲解（深蹲、硬拉、卧推等）
- 运动营养基础（减脂、增肌饮食原则）
- 训练计划设计原理（组数、次数、频率）
- 常见体态问题和矫正思路

# 回答规则
1. **参考资料优先**：优先基于下方参考资料回答。如果资料充分，在回答末尾标注参考编号（如[Ref1]）。
2. **诚实边界**：如果参考资料不足以回答问题，直接说明"我目前的知识库中没有这方面的详细信息"，然后给出你的通用建议。
3. **结构化输出**：先给核心结论（1-2句话），再展开详细说明。涉及步骤时用编号列表。
4. **安全提醒**：你不替代医生或物理治疗师。遇到运动损伤、康复类问题，引导用户咨询专业医疗机构。

## 参考资料
{context_text or "暂无相关参考资料"}

## 对话历史
{memory_text or "无历史对话"}

## 用户问题
{state['user_input']}

请回答："""

    state["_prompt"] = prompt  # type: ignore
    if state.get("_streaming"):
        state["result"] = ""
        return state

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=config.model_max_tokens,
        temperature=config.model_temperature,
        top_p=config.model_top_p,
    )
    answer = llm.generate(prompt)
    state["result"] = answer
    return state


def build_chat_subgraph():
    """Build Chat RAG subgraph: retrieve -> generate -> END."""
    builder = StateGraph(RouterState)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate", generate_node)
    builder.set_entry_point("retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)
    return builder.compile()

"""Chat subgraph — RAG knowledge Q&A."""
import logging

from langgraph.graph import StateGraph, END

from app.config import config
from app.graph.prompt_builder import PromptBuilder
from app.graph.state import RouterState, record_execution
from app.graph.structured_state import add_knowledge_sources
from app.graph.subgraphs.rag_context import build_rag_context, retrieve_knowledge

logger = logging.getLogger(__name__)

CHAT_GENERATION_MAX_TOKENS = 512
CHAT_GENERATION_TEMPERATURE = 0.0
CHAT_GENERATION_TOP_P = 1.0


def retrieve_node(state: RouterState) -> RouterState:
    """Retrieve relevant documents from the shared knowledge base."""
    result = retrieve_knowledge(
        state["user_input"],
        top_k=config.retriever_top_k,
        threshold=config.retriever_threshold,
    )
    retrieved = result.data if result.ok and result.data else []
    state["_retrieved"] = retrieved  # type: ignore
    state["_retrieval_meta"] = result.meta  # type: ignore
    backend = str(result.meta.get("backend") or "memory")
    retrieval_mode = str(result.meta.get("mode") or "")
    fallback_from = result.meta.get("fallback_from")
    public_mode = (
        "memory_fallback"
        if fallback_from
        else (f"memory_{retrieval_mode}" if backend == "memory" and retrieval_mode else backend)
    )
    record_execution(
        state,
        "rag",
        public_mode,
        degraded=bool(fallback_from) or retrieval_mode == "keyword" or not result.ok,
        detail=(
            "Vector store unavailable; using in-memory retrieval"
            if fallback_from
            else (
                "Embedding model unavailable; using keyword matching"
                if retrieval_mode == "keyword"
                else ("Retrieval failed" if not result.ok else "")
            )
        ),
    )
    logger.info(f"Retrieved {len(retrieved)} chunks for: {state['user_input'][:50]}")
    return state


def generate_node(state: RouterState) -> RouterState:
    """Generate answer based on retrieved context + memory + user input."""
    from app.llm.providers import create_llm

    retrieved = state.get("_retrieved", [])  # type: ignore
    context_text, sources = build_rag_context(retrieved)
    state["_sources"] = sources  # type: ignore
    add_knowledge_sources(state, sources)

    prompt = PromptBuilder.chat_answer(
        state,
        context_text=context_text,
        sources=sources,
    )
    state["_prompt_meta"]["generation"] = {
        "max_tokens": CHAT_GENERATION_MAX_TOKENS,
        "temperature": CHAT_GENERATION_TEMPERATURE,
        "top_p": CHAT_GENERATION_TOP_P,
    }
    if state.get("_streaming"):
        state["result"] = ""
        return state

    llm = create_llm(
        state.get("_model_id"),
        max_tokens=CHAT_GENERATION_MAX_TOKENS,
        temperature=CHAT_GENERATION_TEMPERATURE,
        top_p=CHAT_GENERATION_TOP_P,
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

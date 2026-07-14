"""Diet subgraph — RAG-enhanced personalized diet recommendations."""
import json
import logging
from typing import Any, Literal, Optional, Tuple

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.config import config
from app.graph.prompt_builder import PromptBuilder
from app.graph.state import RouterState, record_execution
from app.graph.structured_state import add_knowledge_sources, merge_profile
from app.graph.subgraphs.rag_context import build_rag_context, retrieve_knowledge

logger = logging.getLogger(__name__)


class DietProfile(BaseModel):
    """Validated, bounded profile extracted from one diet request."""

    height_cm: Optional[float] = Field(default=None, ge=80, le=250)
    weight_kg: Optional[float] = Field(default=None, ge=20, le=400)
    gender: Literal["男", "女", "未知"] = "未知"
    goal: Literal["减脂", "增肌", "保持", "未知"] = "未知"
    preferences: str = Field(default="未知", max_length=500)

    @field_validator("height_cm", "weight_kg", mode="before")
    @classmethod
    def normalize_optional_number(cls, value: Any) -> Any:
        if value is None or str(value).strip().lower() in {"", "未知", "unknown", "null"}:
            return None
        return value

    @field_validator("gender", mode="before")
    @classmethod
    def normalize_gender(cls, value: Any) -> str:
        normalized = str(value or "未知").strip()
        return {"男性": "男", "女性": "女"}.get(normalized, normalized)

    @field_validator("goal", mode="before")
    @classmethod
    def normalize_goal(cls, value: Any) -> str:
        normalized = str(value or "未知").strip()
        return {"减重": "减脂", "维持": "保持"}.get(normalized, normalized)

    @field_validator("preferences", mode="before")
    @classmethod
    def normalize_preferences(cls, value: Any) -> str:
        if value is None:
            return "未知"
        if isinstance(value, list):
            return "、".join(str(item) for item in value)
        return str(value).strip() or "未知"


def parse_diet_profile(profile_text: str) -> Tuple[DietProfile, Optional[str]]:
    """Parse one LLM JSON object or return a safe unknown profile."""
    if not isinstance(profile_text, str):
        return DietProfile(), "profile_output_not_text"
    start = profile_text.find("{")
    end = profile_text.rfind("}")
    if start < 0 or end < start:
        return DietProfile(), "profile_json_missing"
    try:
        raw = json.loads(profile_text[start:end + 1])
        if not isinstance(raw, dict):
            return DietProfile(), "profile_json_not_object"
        return DietProfile.model_validate(raw), None
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return DietProfile(), "profile_validation_failed"


def extract_profile_node(state: RouterState) -> RouterState:
    """Extract user body parameters and goals."""
    from app.config import config
    from app.llm.loader import LLMLoader

    prompt = PromptBuilder.diet_profile_extraction(state["user_input"])

    llm = LLMLoader(
        model_path=config.model_path,
        device=config.model_device,
        max_tokens=256,
        temperature=0.2,
    )
    profile_text = llm.generate(prompt)
    profile, warning = parse_diet_profile(profile_text)
    state["_user_profile"] = profile.model_dump()  # type: ignore
    merge_profile(state, profile.model_dump())
    if warning:
        state.setdefault("_route_execution_warnings", []).append(
            f"diet_profile_fallback:{warning}"
        )
    return state


def retrieve_nutrition_node(state: RouterState) -> RouterState:
    """RAG retrieval: search shared nutrition knowledge base."""
    profile = state.get("_user_profile", {})
    query = f"{state['user_input']} {json.dumps(profile, ensure_ascii=False)}"
    result = retrieve_knowledge(
        query,
        top_k=config.retriever_top_k,
        threshold=config.retriever_threshold,
    )
    state["_retrieved"] = result.data if result.ok and result.data else []  # type: ignore
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
            "Milvus unavailable; using in-memory retrieval"
            if fallback_from
            else (
                "Embedding model unavailable; using keyword matching"
                if retrieval_mode == "keyword"
                else ("Retrieval failed" if not result.ok else "")
            )
        ),
    )
    return state


def recommend_node(state: RouterState) -> RouterState:
    """Generate personalized diet recommendations."""
    from app.config import config
    from app.llm.loader import LLMLoader

    profile = state.get("_user_profile", {})
    retrieved = state.get("_retrieved", [])  # type: ignore
    context_text, sources = build_rag_context(retrieved)
    state["_sources"] = sources  # type: ignore
    add_knowledge_sources(state, sources)

    prompt = PromptBuilder.diet_recommendation(
        state,
        profile=profile,
        context_text=context_text,
    )
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

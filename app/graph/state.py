"""LangGraph global state definition."""
from typing import Any, Dict, List, Optional, TypedDict


def record_execution(
    state: "RouterState",
    component: str,
    mode: str,
    *,
    degraded: bool = False,
    detail: str = "",
) -> None:
    """Append a public-safe execution trace without leaking credentials."""
    item: Dict[str, Any] = {
        "component": component,
        "mode": mode,
        "degraded": degraded,
    }
    if detail:
        item["detail"] = detail
    trace = state.setdefault("_execution", [])
    if item not in trace:
        trace.append(item)


class RouterState(TypedDict, total=False):
    """Router-level global state shared across all subgraphs.

    Uses total=False so subgraphs can attach transient internal keys
    (like _prompt, _retrieved, _thought, _tools_to_call).
    """

    user_input: str
    user_id: str
    conversation_id: str
    intent: str  # "search" | "motion" | "diet" | "chat" | "mcp"
    memory: List[Dict[str, str]]
    result: str
    error: Optional[str]
    _prompt: str  # Reserved for streaming endpoints; built by subgraphs.
    _prompt_meta: Dict[str, Any]
    _structured_state: Dict[str, Any]
    _long_term_memories: List[Dict[str, Any]]
    _streaming: bool  # Build the final prompt without generating twice.
    _route_scores: Dict[str, float]
    _route_confidence: float
    _route_reason: str
    _route_source: str
    _route_matches: List[str]
    _route_ambiguity_signals: List[str]
    _primary_intent: str
    _secondary_intents: List[str]
    _route_plan: List[str]
    _multi_intent_reason: str
    _needs_clarification: bool
    _route_execution_plan: List[str]
    _route_execution_cursor: int
    _active_intent: str
    _route_results: List[Dict[str, Any]]
    _route_execution_warnings: List[str]
    _execution: List[Dict[str, Any]]

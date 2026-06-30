"""LangGraph global state definition."""
from typing import Any, Dict, List, Optional, TypedDict


class RouterState(TypedDict, total=False):
    """Router-level global state shared across all subgraphs.

    Uses total=False so subgraphs can attach transient internal keys
    (like _prompt, _retrieved, _thought, _tools_to_call).
    """

    user_input: str
    user_id: str
    intent: str  # "search" | "motion" | "diet" | "chat" | "mcp"
    memory: List[Dict[str, str]]
    result: str
    error: Optional[str]
    _prompt: str  # Reserved for streaming endpoints; built by subgraphs.
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

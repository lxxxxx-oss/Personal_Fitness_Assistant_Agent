"""Helpers for the current conversation working state.

`_structured_state` is a compact runtime state for routing, prompt building, and
future context compression. It is not the long-term memory store.
"""
import copy
import json
from typing import Any, Dict, Mapping, MutableMapping, Sequence

from app.graph.state import RouterState


DEFAULT_STRUCTURED_STATE: Dict[str, Any] = {
    "task": {},
    "decisions": [],
    "tool_results_summary": [],
    "profile": {},
    "knowledge_sources": [],
    "user_context": {},
}


def ensure_structured_state(state: RouterState) -> Dict[str, Any]:
    structured = state.get("_structured_state")
    if not isinstance(structured, dict):
        structured = copy.deepcopy(DEFAULT_STRUCTURED_STATE)
        state["_structured_state"] = structured
        return structured
    for key, value in DEFAULT_STRUCTURED_STATE.items():
        if key not in structured:
            structured[key] = copy.deepcopy(value)
    return structured


def set_task(state: RouterState, task: Mapping[str, Any]) -> None:
    ensure_structured_state(state)["task"] = dict(task)


def add_decision(state: RouterState, decision: Mapping[str, Any]) -> None:
    decisions = ensure_structured_state(state).setdefault("decisions", [])
    decisions.append(dict(decision))


def merge_profile(state: RouterState, profile: Mapping[str, Any]) -> None:
    current = ensure_structured_state(state).setdefault("profile", {})
    for key, value in profile.items():
        if value not in (None, "", "未知"):
            current[key] = value


def add_knowledge_sources(state: RouterState, sources: Sequence[Any]) -> None:
    current = ensure_structured_state(state).setdefault("knowledge_sources", [])
    for source in sources:
        if source and source not in current:
            current.append(source)


def add_tool_preview(
    state: RouterState,
    *,
    intent: str,
    tool: str,
    summary: str,
    data_ref: str = "",
) -> None:
    previews = ensure_structured_state(state).setdefault("tool_results_summary", [])
    item = {
        "intent": intent,
        "tool": tool,
        "summary": truncate_text(summary, 800),
    }
    if data_ref:
        item["data_ref"] = data_ref
    previews.append(item)


def truncate_text(value: Any, max_chars: int = 1200) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n...[truncated]"


def json_preview(value: Any, max_chars: int = 1200) -> str:
    return truncate_text(json.dumps(value, ensure_ascii=False, indent=2), max_chars)

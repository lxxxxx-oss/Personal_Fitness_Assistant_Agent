"""Shared formatting for RAG evidence blocks and public source metadata."""
from typing import Any, Dict, Iterable, List, Tuple

from app.tools.registry import ToolRegistry, build_default_tool_registry


_rag_tool_registry: ToolRegistry = None


def get_rag_tool_registry() -> ToolRegistry:
    """Return the shared registry used by Knowledge/RAG retrieval."""
    global _rag_tool_registry
    if _rag_tool_registry is None:
        _rag_tool_registry = build_default_tool_registry()
    return _rag_tool_registry


def retrieve_knowledge(
    query: str,
    top_k: int = 5,
    threshold: float = 0.3,
):
    """Retrieve Knowledge/RAG evidence through ToolRegistry."""
    registry = get_rag_tool_registry()
    return registry.execute(
        "knowledge.retrieve",
        {"query": query, "top_k": top_k, "threshold": threshold},
        context={"allowed_permissions": ["read_knowledge"]},
    )


def build_rag_context(
    retrieved: Iterable[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    """Build numbered evidence text and a stable, deduplicated source list."""
    blocks: List[str] = []
    sources: List[str] = []
    for item in retrieved:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        source = str(item.get("source") or "").strip()
        section_path = str(item.get("section_path") or "").strip()
        source_label = source or "未标注来源"
        ref_index = len(blocks) + 1
        lines = [f"[Ref{ref_index}]", f"来源: {source_label}"]
        if section_path:
            lines.append(f"章节: {section_path}")
        lines.append(f"内容: {content}")
        blocks.append("\n".join(lines))
        if source and source not in sources:
            sources.append(source)
    return "\n\n".join(blocks), sources

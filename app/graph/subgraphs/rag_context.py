"""Shared formatting for RAG evidence blocks and public source metadata."""
from typing import Any, Dict, Iterable, List, Tuple


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
        source_label = source or "未标注来源"
        ref_index = len(blocks) + 1
        blocks.append(
            f"[Ref{ref_index}]\n来源: {source_label}\n内容: {content}"
        )
        if source and source not in sources:
            sources.append(source)
    return "\n\n".join(blocks), sources

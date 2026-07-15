"""Deterministic extractive summaries for one persisted conversation."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.memory.conversation_store import ConversationStore


ROLE_LABELS = {
    "user": "用户",
    "assistant": "助手",
    "system": "系统",
    "compact": "摘要",
}


def build_extractive_summary(
    previous_summary: str,
    messages: Sequence[Mapping[str, str]],
    *,
    max_chars: int = 1200,
    per_message_chars: int = 240,
) -> str:
    """Build a bounded summary from original snippets without model generation."""
    max_chars = max(200, int(max_chars))
    per_message_chars = max(40, int(per_message_chars))
    sections: List[str] = []
    normalized_previous = _normalize(previous_summary)
    if normalized_previous:
        sections.append(f"已有会话摘要：\n{normalized_previous}")

    lines = []
    for message in messages:
        content = _normalize(str(message.get("content", "")))
        if not content:
            continue
        if len(content) > per_message_chars:
            content = content[: per_message_chars - 3].rstrip() + "..."
        role = ROLE_LABELS.get(str(message.get("role", "")), "消息")
        lines.append(f"- {role}：{content}")
    if lines:
        sections.append("新增对话摘录：\n" + "\n".join(lines))

    summary = "\n\n".join(sections) or "暂无可摘要内容"
    if len(summary) <= max_chars:
        return summary
    marker = "\n...[摘要按字符预算压缩]...\n"
    available = max_chars - len(marker)
    head_chars = available // 2
    tail_chars = available - head_chars
    return summary[:head_chars].rstrip() + marker + summary[-tail_chars:].lstrip()


def maybe_compact_conversation(
    store: ConversationStore,
    conversation_id: str,
    user_id: str,
    *,
    trigger_chars: int,
    keep_recent_messages: int = 6,
    max_summary_chars: int = 1200,
) -> Dict[str, Any]:
    """Persist an extractive summary when uncompacted older messages cross a threshold."""
    trigger_chars = max(1, int(trigger_chars))
    keep_recent_messages = max(2, int(keep_recent_messages))
    uncompacted = store.get_uncompacted_messages(conversation_id, user_id)
    candidates = uncompacted[:-keep_recent_messages]
    candidate_chars = sum(len(item.get("content", "")) for item in candidates)
    if not candidates:
        return _result("insufficient_history", candidate_chars=candidate_chars)
    if candidate_chars < trigger_chars:
        return _result("below_threshold", candidate_chars=candidate_chars)

    active = store.get_active_summary(conversation_id, user_id)
    summary = build_extractive_summary(
        str(active.get("content", "")) if active else "",
        candidates,
        max_chars=max_summary_chars,
    )
    saved = store.save_compact_summary(
        conversation_id,
        user_id,
        summary,
        candidates[-1]["id"],
    )
    return {
        "triggered": True,
        "updated": True,
        "reason": "threshold_reached",
        "summary_id": saved["id"],
        "summary_chars": len(saved["content"]),
        "compacted_message_count": len(candidates),
        "candidate_chars": candidate_chars,
        "last_compacted_message_id": saved["last_compacted_message_id"],
        "remaining_message_count": len(uncompacted) - len(candidates),
        "mode": "deterministic_extractive",
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _result(reason: str, *, candidate_chars: int) -> Dict[str, Any]:
    return {
        "triggered": False,
        "updated": False,
        "reason": reason,
        "candidate_chars": candidate_chars,
        "mode": "deterministic_extractive",
    }

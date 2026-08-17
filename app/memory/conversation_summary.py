"""Deterministic extractive summaries for one persisted conversation."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.memory.conversation_store import ConversationStore
from app.memory.token_budget import estimate_tokens, within_budget


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


def build_structured_summary(
    previous_summary: str,
    messages: Sequence[Mapping[str, str]],
    *,
    max_chars: int = 1200,
    max_tokens: int = 360,
    per_message_chars: int = 180,
) -> str:
    """Build a bounded JSON summary whose facts remain traceable to snippets."""
    max_chars = max(200, int(max_chars))
    max_tokens = max(80, int(max_tokens))
    evidence: List[Dict[str, str]] = []
    reused = False
    normalized_previous = _normalize(previous_summary)
    if normalized_previous:
        try:
            previous = json.loads(previous_summary)
            for item in previous.get("evidence", []):
                if isinstance(item, dict) and item.get("content"):
                    evidence.append(
                        {
                            "role": str(item.get("role", "message")),
                            "content": _normalize(str(item["content"])),
                        }
                    )
            reused = bool(evidence)
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence.append(
                {
                    "role": "summary",
                    "content": normalized_previous[:per_message_chars],
                }
            )
            reused = True

    for message in messages:
        content = _normalize(str(message.get("content", "")))
        if not content:
            continue
        evidence.append(
            {
                "role": str(message.get("role", "message")),
                "content": content[:per_message_chars],
            }
        )

    deduplicated: List[Dict[str, str]] = []
    seen = set()
    for item in evidence:
        key = (item["role"], item["content"])
        if key not in seen:
            deduplicated.append(item)
            seen.add(key)
    evidence = deduplicated

    def render() -> str:
        payload = {
            "version": 1,
            "mode": "deterministic_evidence",
            "status": "已有会话摘要已复用" if reused else "首次压缩",
            "signals": _extract_signals(evidence),
            "evidence": evidence,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    summary = render()
    while len(evidence) > 1 and not within_budget(
        summary,
        max_chars=max_chars,
        max_tokens=max_tokens,
    ):
        signal_indexes = {
            index
            for indexes in _extract_signals(evidence).values()
            for index in indexes
        }
        removable = next(
            (index for index in range(len(evidence)) if index not in signal_indexes),
            0,
        )
        evidence.pop(removable)
        summary = render()
    while evidence and not within_budget(
        summary,
        max_chars=max_chars,
        max_tokens=max_tokens,
    ):
        content = evidence[0]["content"]
        if len(content) <= 20:
            evidence.clear()
        else:
            evidence[0]["content"] = content[: max(20, int(len(content) * 0.8))]
        summary = render()
    return summary


def maybe_compact_conversation(
    store: ConversationStore,
    conversation_id: str,
    user_id: str,
    *,
    trigger_chars: int,
    trigger_tokens: int = 900,
    keep_recent_messages: int = 12,
    max_summary_chars: int = 1200,
    max_summary_tokens: int = 360,
) -> Dict[str, Any]:
    """Persist an evidence summary when older messages cross either budget."""
    trigger_chars = max(1, int(trigger_chars))
    trigger_tokens = max(1, int(trigger_tokens))
    keep_recent_messages = max(2, int(keep_recent_messages))
    uncompacted = store.get_uncompacted_messages(conversation_id, user_id)
    candidates = uncompacted[:-keep_recent_messages]
    candidate_chars = sum(len(item.get("content", "")) for item in candidates)
    candidate_tokens = sum(
        estimate_tokens(str(item.get("content", ""))) for item in candidates
    )
    if not candidates:
        return _result(
            "insufficient_history",
            candidate_chars=candidate_chars,
            candidate_tokens=candidate_tokens,
            trigger_chars=trigger_chars,
            trigger_tokens=trigger_tokens,
        )
    if candidate_chars < trigger_chars and candidate_tokens < trigger_tokens:
        return _result(
            "below_threshold",
            candidate_chars=candidate_chars,
            candidate_tokens=candidate_tokens,
            trigger_chars=trigger_chars,
            trigger_tokens=trigger_tokens,
        )

    active = store.get_active_summary(conversation_id, user_id)
    summary = build_structured_summary(
        str(active.get("content", "")) if active else "",
        candidates,
        max_chars=max_summary_chars,
        max_tokens=max_summary_tokens,
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
        "candidate_tokens": candidate_tokens,
        "trigger_chars": trigger_chars,
        "trigger_tokens": trigger_tokens,
        "last_compacted_message_id": saved["last_compacted_message_id"],
        "remaining_message_count": len(uncompacted) - len(candidates),
        "mode": "deterministic_evidence",
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_signals(evidence: Sequence[Mapping[str, str]]) -> Dict[str, List[int]]:
    patterns = {
        "goals": re.compile(r"目标|减脂|增肌|塑形|备赛"),
        "constraints": re.compile(r"伤|疼|痛|过敏|忌口|不能|避免"),
        "preferences": re.compile(r"喜欢|偏好|习惯|通常|每周|每天"),
    }
    signals: Dict[str, List[int]] = {key: [] for key in patterns}
    for index, item in enumerate(evidence):
        content = str(item.get("content", ""))
        for key, pattern in patterns.items():
            if pattern.search(content):
                signals[key].append(index)
    return {key: values[-3:] for key, values in signals.items() if values}


def _result(
    reason: str,
    *,
    candidate_chars: int,
    candidate_tokens: int,
    trigger_chars: int,
    trigger_tokens: int,
) -> Dict[str, Any]:
    return {
        "triggered": False,
        "updated": False,
        "reason": reason,
        "candidate_chars": candidate_chars,
        "candidate_tokens": candidate_tokens,
        "trigger_chars": trigger_chars,
        "trigger_tokens": trigger_tokens,
        "mode": "deterministic_evidence",
    }

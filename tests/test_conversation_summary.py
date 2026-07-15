from app.memory.conversation_store import ConversationStore
from app.memory.conversation_summary import (
    build_extractive_summary,
    maybe_compact_conversation,
)


def _add_turns(store, conversation_id, count, *, content_size=20):
    for index in range(count):
        store.add_turn(
            conversation_id,
            "u1",
            f"第{index}个问题" + "问" * content_size,
            f"第{index}个回答" + "答" * content_size,
        )


def test_extractive_summary_is_bounded_and_uses_original_snippets():
    summary = build_extractive_summary(
        "用户目标是减脂",
        [
            {"role": "user", "content": "膝盖有旧伤 " * 40},
            {"role": "assistant", "content": "建议低冲击训练 " * 40},
        ],
        max_chars=200,
        per_message_chars=100,
    )

    assert len(summary) <= 200
    assert "用户目标是减脂" in summary
    assert "建议低冲击训练" in summary
    assert "摘要按字符预算压缩" in summary


def test_compaction_waits_until_old_messages_cross_threshold(tmp_path):
    store = ConversationStore(str(tmp_path / "memory.db"))
    conversation_id = store.get_or_create_conversation("u1")
    _add_turns(store, conversation_id, 4, content_size=5)

    result = maybe_compact_conversation(
        store,
        conversation_id,
        "u1",
        trigger_chars=1000,
        keep_recent_messages=6,
    )

    assert result["updated"] is False
    assert result["reason"] == "below_threshold"
    assert store.get_active_summary(conversation_id, "u1") is None


def test_compaction_keeps_recent_three_turns_and_advances_boundary(tmp_path):
    store = ConversationStore(str(tmp_path / "memory.db"))
    conversation_id = store.get_or_create_conversation("u1")
    _add_turns(store, conversation_id, 6)

    result = maybe_compact_conversation(
        store,
        conversation_id,
        "u1",
        trigger_chars=1,
        keep_recent_messages=6,
        max_summary_chars=500,
    )

    assert result["updated"] is True
    assert result["compacted_message_count"] == 6
    assert result["remaining_message_count"] == 6
    assert len(store.get_uncompacted_messages(conversation_id, "u1")) == 6
    assert store.get_active_summary(conversation_id, "u1")["content"]


def test_incremental_compaction_reuses_active_summary_without_reprocessing_boundary(
    tmp_path,
):
    store = ConversationStore(str(tmp_path / "memory.db"))
    conversation_id = store.get_or_create_conversation("u1")
    _add_turns(store, conversation_id, 6)
    first = maybe_compact_conversation(
        store,
        conversation_id,
        "u1",
        trigger_chars=1,
        keep_recent_messages=6,
    )
    first_summary = store.get_active_summary(conversation_id, "u1")["content"]
    _add_turns(store, conversation_id, 3)

    second = maybe_compact_conversation(
        store,
        conversation_id,
        "u1",
        trigger_chars=1,
        keep_recent_messages=6,
    )
    second_summary = store.get_active_summary(conversation_id, "u1")["content"]

    assert second["updated"] is True
    assert first["last_compacted_message_id"] != second["last_compacted_message_id"]
    assert "已有会话摘要" in second_summary
    assert "第0个问题" in second_summary
    assert "第5个回答" in second_summary
    assert len(store.get_uncompacted_messages(conversation_id, "u1")) == 6

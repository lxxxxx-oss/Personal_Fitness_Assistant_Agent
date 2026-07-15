"""SQLite conversation persistence tests."""

import sqlite3

import pytest

from app.memory.conversation_store import ConversationStore


def test_conversation_store_creates_and_restores_messages(tmp_path):
    store = ConversationStore(str(tmp_path / "memory.db"))
    conversation_id = store.get_or_create_conversation("u1")

    store.add_turn(conversation_id, "u1", "hello", "hi")
    messages = store.get_messages(conversation_id, "u1")

    assert messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    assert store.get_or_create_conversation("u1") == conversation_id


def test_conversation_store_archives_user_conversations(tmp_path):
    store = ConversationStore(str(tmp_path / "memory.db"))
    conversation_id = store.get_or_create_conversation("u1")
    assert conversation_id

    store.archive_user_conversations("u1")

    assert store.get_latest_active_conversation("u1") is None


def test_add_turn_is_atomic_and_increments_conversation_once(tmp_path):
    db_path = tmp_path / "memory.db"
    store = ConversationStore(str(db_path))
    conversation_id = store.get_or_create_conversation("u1")

    store.add_turn(conversation_id, "u1", "问题", "回答")

    with sqlite3.connect(db_path) as conn:
        version = conn.execute(
            "SELECT version FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()[0]
    assert version == 1
    assert store.get_messages(conversation_id, "u1") == [
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答"},
    ]


def test_compact_summary_advances_boundary_and_replaces_previous(tmp_path):
    db_path = tmp_path / "memory.db"
    store = ConversationStore(str(db_path))
    conversation_id = store.get_or_create_conversation("u1")
    store.add_turn(conversation_id, "u1", "第一问", "第一答")
    first_records = store.get_message_records(conversation_id, "u1")
    store.add_turn(conversation_id, "u1", "第二问", "第二答")

    first = store.save_compact_summary(
        conversation_id,
        "u1",
        "第一次摘要",
        first_records[-1]["id"],
    )

    assert store.get_active_summary(conversation_id, "u1")["content"] == "第一次摘要"
    assert [item["content"] for item in store.get_uncompacted_messages(
        conversation_id,
        "u1",
    )] == ["第二问", "第二答"]

    all_records = store.get_message_records(conversation_id, "u1")
    second = store.save_compact_summary(
        conversation_id,
        "u1",
        "第二次摘要",
        all_records[-1]["id"],
    )

    assert second["id"] != first["id"]
    assert store.get_active_summary(conversation_id, "u1")["content"] == "第二次摘要"
    assert store.get_uncompacted_messages(conversation_id, "u1") == []
    with sqlite3.connect(db_path) as conn:
        statuses = conn.execute(
            "SELECT status FROM summaries ORDER BY rowid ASC"
        ).fetchall()
    assert statuses == [("superseded",), ("active",)]


def test_summary_boundary_is_scoped_to_user_and_active_conversation(tmp_path):
    store = ConversationStore(str(tmp_path / "memory.db"))
    conversation_id = store.get_or_create_conversation("u1")
    store.add_turn(conversation_id, "u1", "问题", "回答")
    boundary = store.get_message_records(conversation_id, "u1")[-1]["id"]

    with pytest.raises(ValueError, match="not found"):
        store.save_compact_summary(
            conversation_id,
            "u2",
            "越权摘要",
            boundary,
        )

    store.save_compact_summary(conversation_id, "u1", "合法摘要", boundary)
    store.archive_user_conversations("u1")
    assert store.get_active_summary(conversation_id, "u1") is None

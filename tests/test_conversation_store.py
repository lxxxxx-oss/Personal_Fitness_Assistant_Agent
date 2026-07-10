"""SQLite conversation persistence tests."""

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

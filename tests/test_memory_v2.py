"""Focused regression tests for evidence-based memory and temporary chat."""

from __future__ import annotations

import asyncio
import sqlite3

import app.main as main_module
from app.config import config
from app.memory.conversation_store import ConversationStore
from app.memory.memory_store import MemoryStore


def _enable_memory_v2(monkeypatch) -> None:
    monkeypatch.setattr(config, "memory_v2_enabled", True)
    monkeypatch.setattr(config, "memory_auto_promotion_enabled", True)
    monkeypatch.setattr(config, "memory_soft_injection_enabled", True)
    monkeypatch.setattr(config, "memory_auto_promotion_evidence", 2)
    monkeypatch.setattr(config, "memory_auto_promotion_conversations", 2)
    monkeypatch.setattr(config, "memory_auto_promotion_confidence", 0.82)
    monkeypatch.setattr(config, "memory_soft_min_confidence", 0.62)
    monkeypatch.setattr(config, "memory_observation_ttl_days", 30)


def test_same_message_is_deduplicated_and_cannot_self_promote(tmp_path, monkeypatch):
    _enable_memory_v2(monkeypatch)
    store = MemoryStore(str(tmp_path / "memory.db"))

    first = store.observe_memory(
        user_id="u1",
        kind="preference",
        content="我通常在晚上训练",
        conversation_id="c1",
        message_id="m1",
    )
    repeated = store.observe_memory(
        user_id="u1",
        kind="preference",
        content="我通常在晚上训练",
        conversation_id="c1",
        message_id="m1",
    )

    assert first is not None
    assert repeated is not None
    assert repeated["id"] == first["id"]
    assert repeated["deduplicated"] is True
    assert repeated["evidence_count"] == 1
    assert repeated["conversation_count"] == 1
    assert store.list_memories("u1") == []


def test_low_risk_fact_promotes_only_after_independent_conversation_evidence(
    tmp_path, monkeypatch
):
    _enable_memory_v2(monkeypatch)
    store = MemoryStore(str(tmp_path / "memory.db"))

    observation = store.observe_memory(
        user_id="u1",
        kind="preference",
        content="我通常在晚上训练",
        conversation_id="c1",
        message_id="m1",
    )
    promoted = store.observe_memory(
        user_id="u1",
        kind="preference",
        content="我通常在晚上训练",
        conversation_id="c2",
        message_id="m2",
    )

    assert observation is not None
    assert observation["status"] == "observed"
    assert promoted is not None
    assert promoted["promoted"] is True
    assert promoted["automatic"] is True
    assert store.list_observations("u1", status="promoted")[0][
        "promoted_memory_id"
    ] == promoted["id"]
    assert store.list_memories("u1")[0]["content"] == "我通常在晚上训练"


def test_sensitive_observation_requires_review_and_is_never_soft_injected(
    tmp_path, monkeypatch
):
    _enable_memory_v2(monkeypatch)
    store = MemoryStore(str(tmp_path / "memory.db"))

    observation = store.observe_memory(
        user_id="u1",
        kind="constraint",
        content="我的膝盖有旧伤",
        conversation_id="c1",
        message_id="m1",
    )
    reinforced = store.observe_memory(
        user_id="u1",
        kind="constraint",
        content="我的膝盖有旧伤",
        conversation_id="c2",
        message_id="m2",
    )

    assert observation is not None
    assert reinforced is not None
    assert reinforced["risk_level"] == "sensitive"
    assert reinforced["status"] == "review_required"
    assert store.list_memories("u1") == []
    assert store.search_soft_memories("u1", "膝盖训练怎么安排") == []


def test_secret_content_is_rejected_before_any_memory_row_is_written(
    tmp_path, monkeypatch
):
    _enable_memory_v2(monkeypatch)
    db_path = tmp_path / "memory.db"
    store = MemoryStore(str(db_path))

    result = store.observe_memory(
        user_id="u1",
        kind="note",
        content="我的 API key 是 abc123",
        conversation_id="c1",
        message_id="m1",
    )

    assert result is None
    assert store.list_observations("u1", status="all") == []
    assert store.list_memories("u1") == []
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0] == 0


def test_undo_auto_promotion_reopens_observation_and_deletes_durable_memory(
    tmp_path, monkeypatch
):
    _enable_memory_v2(monkeypatch)
    store = MemoryStore(str(tmp_path / "memory.db"))
    store.observe_memory(
        user_id="u1",
        kind="preference",
        content="我通常在晚上训练",
        conversation_id="c1",
        message_id="m1",
    )
    promoted = store.observe_memory(
        user_id="u1",
        kind="preference",
        content="我通常在晚上训练",
        conversation_id="c2",
        message_id="m2",
    )
    promote_event = next(
        item
        for item in store.list_memory_events("u1")
        if item["event_type"] == "promote"
    )

    assert promoted is not None
    assert store.undo_memory_event("u1", promote_event["id"]) is True
    assert store.list_memories("u1") == []
    reopened = store.list_observations("u1", status="open")[0]
    assert reopened["status"] == "observed"
    assert reopened["promoted_memory_id"] is None
    assert next(
        item
        for item in store.list_memory_events("u1")
        if item["id"] == promote_event["id"]
    )["undone_at"]


def test_stale_observation_expires_and_is_removed_from_open_recall(
    tmp_path, monkeypatch
):
    _enable_memory_v2(monkeypatch)
    db_path = tmp_path / "memory.db"
    store = MemoryStore(str(db_path))
    observation = store.observe_memory(
        user_id="u1",
        kind="preference",
        content="我通常在晚上训练",
        conversation_id="c1",
        message_id="m1",
    )
    assert observation is not None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE memory_observations SET expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", observation["id"]),
        )

    assert store.list_observations("u1", status="open") == []
    assert store.get_observation("u1", observation["id"])["status"] == "expired"
    assert any(
        item["event_type"] == "expire"
        for item in store.list_memory_events("u1")
    )


def test_temporary_chat_keeps_only_process_local_short_term_context(
    tmp_path, monkeypatch
):
    conversation_store = ConversationStore(str(tmp_path / "conversation.db"))
    memory_store = MemoryStore(str(tmp_path / "memory.db"))
    monkeypatch.setattr(main_module, "_conversation_store", conversation_store)
    monkeypatch.setattr(main_module, "_memory_store", memory_store)
    monkeypatch.setattr(main_module, "_sessions", {})
    monkeypatch.setattr(
        "app.llm.providers.resolve_model_id",
        lambda model_id: model_id or "test-model",
    )

    first = main_module._prepare_chat_sync(
        "u1",
        "我通常在晚上训练",
        None,
        None,
        streaming=False,
        temporary=True,
    )
    asyncio.run(main_module._persist_prepared_chat(first, "好的"))
    second = main_module._prepare_chat_sync(
        "u1",
        "那我今天怎么安排？",
        first.conversation_id,
        None,
        streaming=False,
        temporary=True,
    )

    assert first.conversation_id.startswith("tmp_")
    assert second.memory.get_all() == [
        {"role": "user", "content": "我通常在晚上训练"},
        {"role": "assistant", "content": "好的"},
    ]
    assert second.state["_long_term_memories"] == []
    assert second.state["_soft_memories"] == []
    assert conversation_store.list_conversations("u1") == []
    assert memory_store.list_memories("u1") == []
    assert memory_store.list_observations("u1", status="all") == []

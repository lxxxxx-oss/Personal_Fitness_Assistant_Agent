from app.memory.memory_store import (
    MemoryStore,
    extract_explicit_memory_content,
    infer_explicit_memory_kind,
)
from app.tools.types import ToolResult


class FakeSemanticRetriever:
    def __init__(self):
        self.docs = []
        self.sources = []
        self.fail = False

    def add_documents(self, docs, sources=None):
        if self.fail:
            return ToolResult.fail("NETWORK_ERROR", "milvus unavailable")
        self.docs.extend(docs)
        self.sources.extend(list(sources or []))
        return ToolResult.ok(data={"upserted": len(docs)}, backend="milvus")

    def search(self, query, top_k=5, threshold=0.1):
        if not self.sources:
            return ToolResult.ok(data=[], backend="milvus")
        return ToolResult.ok(
            data=[
                {
                    "content": self.docs[0],
                    "score": 0.92,
                    "index": 1,
                    "source": self.sources[0],
                }
            ],
            backend="milvus",
        )


def test_memory_store_crud_and_logical_delete(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.db"))

    created = store.create_memory(
        user_id="u1",
        kind="preference",
        content="不喜欢高糖饮料",
        source_type="manual_import",
        importance=0.7,
    )

    assert created["kind"] == "preference"
    assert created["status"] == "active"

    listed = store.list_memories("u1")
    assert [item["id"] for item in listed] == [created["id"]]

    updated = store.update_memory(
        user_id="u1",
        memory_id=created["id"],
        updates={"content": "不喜欢含糖饮料", "importance": 0.9},
    )
    assert updated["content"] == "不喜欢含糖饮料"
    assert updated["importance"] == 0.9

    assert store.delete_memory("u1", created["id"]) is True
    assert store.list_memories("u1") == []
    assert store.list_memories("u1", include_deleted=True)[0]["status"] == "deleted"


def test_memory_store_deduplicates_active_explicit_memory(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.db"))

    first = store.remember_explicit("u1", "请记住 我不喜欢吃香菜")
    second = store.remember_explicit("u1", "记住 我不喜欢吃香菜")

    assert first is not None
    assert second is not None
    assert first["id"] == second["id"]
    assert second["deduplicated"] is True
    assert store.list_memories("u1")[0]["source_type"] == "user_explicit_remember"


def test_sensitive_explicit_memory_requires_candidate_confirmation(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.db"))

    candidate = store.remember_explicit("u1", "请记住 我膝盖有旧伤")

    assert candidate is not None
    assert candidate["candidate"] is True
    assert candidate["privacy_level"] == "health"
    assert store.list_memories("u1") == []

    pending = store.list_candidate_memories("u1")
    assert pending[0]["id"] == candidate["id"]

    confirmed = store.confirm_candidate_memory("u1", candidate["id"])
    assert confirmed is not None
    assert confirmed["content"] == "我膝盖有旧伤"
    assert store.list_candidate_memories("u1") == []
    assert store.list_candidate_memories("u1", status="confirmed")[0]["id"] == candidate["id"]


def test_search_memories_uses_fts_or_like_fallback(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.db"))
    store.create_memory(
        user_id="u1",
        kind="preference",
        content="不喜欢吃香菜",
        source_type="manual_import",
        importance=0.9,
    )

    results = store.search_memories("u1", "今天吃饭不要香菜", limit=5)

    assert results
    assert results[0]["content"] == "不喜欢吃香菜"
    assert results[0]["score"] > 0
    assert store.get_memory("u1", results[0]["id"])["access_count"] == 1


def test_embedding_jobs_process_and_semantic_search_merge(tmp_path):
    retriever = FakeSemanticRetriever()
    store = MemoryStore(
        str(tmp_path / "memory.db"),
        semantic_enabled=True,
        semantic_retriever=retriever,
    )
    created = store.create_memory(
        user_id="u1",
        kind="goal",
        content="目标是提升深蹲力量",
        source_type="manual_import",
        importance=0.9,
    )

    jobs = store.list_embedding_jobs(status="pending")
    assert len(jobs) == 1
    assert jobs[0]["memory_id"] == created["id"]

    processed = store.process_embedding_jobs()
    assert processed == {"processed": 1, "completed": 1, "failed": 0, "enabled": True}
    assert store.list_embedding_jobs(status="completed")[0]["memory_id"] == created["id"]

    results = store.search_memories("u1", "腿部力量进步", limit=5)
    assert results[0]["id"] == created["id"]
    assert results[0]["score"] > 0.4


def test_embedding_job_failure_keeps_main_memory_available(tmp_path):
    retriever = FakeSemanticRetriever()
    retriever.fail = True
    store = MemoryStore(
        str(tmp_path / "memory.db"),
        semantic_enabled=True,
        semantic_retriever=retriever,
    )
    store.create_memory(
        user_id="u1",
        kind="preference",
        content="不喜欢香菜",
        source_type="manual_import",
    )

    processed = store.process_embedding_jobs()

    assert processed["failed"] == 1
    assert store.list_embedding_jobs(status="failed")[0]["attempts"] == 1
    assert store.search_memories("u1", "香菜", limit=5)[0]["content"] == "不喜欢香菜"


def test_explicit_memory_extraction_and_kind_inference():
    assert extract_explicit_memory_content("请记住 我对虾过敏") == "我对虾过敏"
    assert extract_explicit_memory_content("普通闲聊") is None
    assert infer_explicit_memory_kind("我的目标是减脂") == "goal"
    assert infer_explicit_memory_kind("我不喜欢吃香菜") == "preference"

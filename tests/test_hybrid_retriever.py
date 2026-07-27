"""Deterministic coverage for BM25 recall and RRF fusion."""

from app.tools.retriever import BM25Retriever, HybridRetriever
from app.tools.types import ToolResult


class StubDenseRetriever:
    def __init__(self, results=None, *, mode="embedding"):
        self.results = results or {}
        self.mode = mode
        self.calls = []
        self.document_count = 0

    def add_documents(self, docs, sources=None):
        self.document_count += len(docs)
        return ToolResult.ok(
            data={"upserted": len(docs), "removed": 0}, backend="memory"
        )

    def search(self, query, top_k=5, threshold=0.3):
        self.calls.append((query, top_k, threshold))
        return ToolResult.ok(
            data=list(self.results.get(query, []))[:top_k],
            mode=self.mode,
            backend="memory",
        )

    def clear(self):
        self.document_count = 0
        return ToolResult.ok(data={"cleared": True}, backend="memory")


def _item(content, source, index, score=0.9, section_path=""):
    return {
        "content": content,
        "source": source,
        "index": index,
        "score": score,
        "section_path": section_path,
    }


def _knowledge_docs():
    return [
        "# 训练强度\n\n## RPE\nRPE 8 表示还可以完成约 2 次重复。",
        "# 有氧建议\n每周累计进行 150-300分钟 中等强度有氧。",
        "# 深蹲\n保持脊柱中立并让膝盖朝脚尖方向。",
        "# 蛋白质\n增肌阶段应关注总热量与蛋白质摄入。",
        "# 睡眠\n成年人通常需要保持规律且充足的睡眠。",
    ]


def test_exact_term_and_number_are_recalled_by_bm25():
    dense = StubDenseRetriever(
        {
            "RPE": [_item("普通训练建议", "other.txt", 99)],
            "150-300分钟": [_item("拉伸建议", "other.txt", 98)],
        }
    )
    hybrid = HybridRetriever(dense, candidate_k=20, rrf_k=60)
    added = hybrid.add_documents(
        _knowledge_docs(),
        ["intensity.md", "cardio.md", "squat.md", "protein.md", "sleep.md"],
    )

    term_result = hybrid.search("RPE", top_k=5, threshold=0.5)
    number_result = hybrid.search("150-300分钟", top_k=5, threshold=0.5)

    assert added.ok
    assert any(item["source"] == "intensity.md" for item in term_result.data)
    assert any(item["source"] == "cardio.md" for item in number_result.data)
    assert dense.calls == [
        ("RPE", 20, None),
        ("150-300分钟", 20, None),
    ]


def test_hybrid_does_not_filter_dense_candidates_before_rrf():
    low_score = _item("低绝对分但仍应参与排名融合", "dense.md", 7, score=-0.2)
    dense = StubDenseRetriever({"语义问题": [low_score]})
    hybrid = HybridRetriever(dense, candidate_k=20)

    result = hybrid.search("语义问题", top_k=5, threshold=0.99)

    assert result.ok
    assert result.data[0]["source"] == "dense.md"
    assert dense.calls == [("语义问题", 20, None)]
    assert result.meta["dense_threshold_applied"] is False


def test_semantic_rewrite_can_be_recalled_by_dense_route():
    relevant = _item(
        "渐进增加训练负荷有助于提升力量。",
        "strength.md",
        10,
        section_path="训练原则 > 渐进超负荷",
    )
    dense = StubDenseRetriever({"怎样变得更有劲": [relevant]})
    hybrid = HybridRetriever(dense, candidate_k=20)
    hybrid.add_documents(_knowledge_docs(), [f"doc-{i}.md" for i in range(5)])

    result = hybrid.search("怎样变得更有劲", top_k=5)

    assert result.ok
    assert result.data[0]["source"] == "strength.md"
    assert result.data[0]["retrieval_routes"] == ["dense"]


def test_rrf_rewards_two_route_evidence_over_one_route_distractor():
    hybrid = HybridRetriever(StubDenseRetriever(), candidate_k=20, rrf_k=60)
    relevant = _item("相关证据", "gold.md", 1, score=0.81)
    distractor = _item("包含关键词但语义错误", "noise.md", 2, score=9.2)

    fused = hybrid._fuse(
        [relevant],
        [distractor, {**relevant, "score": 3.1}],
    )

    assert fused[0]["source"] == "gold.md"
    assert fused[0]["retrieval_routes"] == ["dense", "bm25"]
    assert fused[0]["score_type"] == "rrf"


def test_same_chunk_is_deduplicated_and_keeps_route_provenance():
    hybrid = HybridRetriever(StubDenseRetriever(), rrf_k=60)
    dense_item = _item("同一片段", "same.md", 1, score=0.8)
    lexical_item = {**dense_item, "score": 4.2}

    fused = hybrid._fuse([dense_item], [lexical_item])

    assert len(fused) == 1
    assert fused[0]["dense_score"] == 0.8
    assert fused[0]["bm25_score"] == 4.2
    assert fused[0]["retrieval_routes"] == ["dense", "bm25"]


def test_dense_keyword_fallback_does_not_masquerade_as_two_route_hybrid():
    dense = StubDenseRetriever(
        {"RPE": [_item("旧关键词降级结果", "old.md", 9)]},
        mode="keyword",
    )
    hybrid = HybridRetriever(dense)
    hybrid.add_documents(
        _knowledge_docs(),
        ["intensity.md", "cardio.md", "squat.md", "protein.md", "sleep.md"],
    )

    result = hybrid.search("RPE")

    assert result.ok
    assert result.meta["mode"] == "bm25"
    assert result.meta["dense_candidates"] == 0
    assert all(item["retrieval_routes"] == ["bm25"] for item in result.data)


def test_bm25_preserves_source_and_section_metadata_and_replaces_stale_source():
    retriever = BM25Retriever()
    first = retriever.add_documents(
        ["# 动作指南\n\n## 深蹲\n深蹲时保持核心稳定。"],
        ["fitness.md"],
    )
    second = retriever.add_documents(
        ["# 动作指南\n\n## 硬拉\n硬拉时保持脊柱中立。"],
        ["fitness.md"],
    )

    result = retriever.search("硬拉")

    assert first.ok and second.ok and result.ok
    assert retriever.document_count == 1
    assert result.data[0]["source"] == "fitness.md"
    assert result.data[0]["section_path"] == "动作指南 > 硬拉"


def test_hybrid_validates_public_search_parameters():
    hybrid = HybridRetriever(StubDenseRetriever())

    assert hybrid.search("query", top_k=0).error_code == "INVALID_PARAM"
    assert hybrid.search("query", threshold=1.1).error_code == "INVALID_PARAM"
    assert hybrid.search("   ").data == []

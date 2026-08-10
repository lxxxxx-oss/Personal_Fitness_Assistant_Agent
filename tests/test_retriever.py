"""Vector retriever tests using mock embeddings."""
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from app.tools.retriever import (
    MemoryRetriever,
    _build_chunk_entries,
    _chinese_sentence_split,
    _resolve_parent_results,
)


class TestChineseSentenceSplit:
    def test_split_by_newline(self):
        text = "First sentence.\nSecond sentence.\n"
        chunks = _chinese_sentence_split(text)
        assert len(chunks) >= 1

    def test_single_sentence(self):
        text = "One complete sentence."
        chunks = _chinese_sentence_split(text)
        assert len(chunks) == 1

    def test_empty_returns_original(self):
        text = ""
        chunks = _chinese_sentence_split(text)
        assert chunks == [""]

    def test_overlong_sentence_is_split_by_max_chunk_chars(self):
        text = "深蹲" * 120
        chunks = _chinese_sentence_split(text, max_chunk_chars=50)

        assert len(chunks) > 1
        assert all(len(chunk) <= 50 for chunk in chunks)
        assert "".join(chunks) == text

    def test_overlong_sentence_supports_overlap(self):
        text = "abcdefghijklmnopqrstuvwxyz"
        chunks = _chinese_sentence_split(
            text,
            max_chunk_chars=10,
            overlap_chars=2,
        )

        assert chunks[:2] == ["abcdefghij", "ijklmnopqr"]
        assert all(len(chunk) <= 10 for chunk in chunks)

    def test_normal_adjacent_chunks_apply_configured_overlap(self):
        text = "第一句内容。第二句内容。第三句内容。"

        chunks = _chinese_sentence_split(
            text,
            max_chunk_chars=13,
            overlap_chars=4,
        )

        assert len(chunks) == 2
        assert chunks[1].startswith(chunks[0][-4:])
        assert all(len(chunk) <= 13 for chunk in chunks)

    def test_build_entries_preserves_heading_path_and_paragraphs(self):
        entries = _build_chunk_entries(
            [
                "# 健身基础动作指南\n"
                "# 来源: 示例来源\n\n"
                "## 深蹲\n"
                "保持核心稳定。\n\n"
                "膝盖方向与脚尖一致。"
            ],
            ["fitness.txt"],
        )

        assert len(entries) == 1
        assert entries[0]["section_path"] == "健身基础动作指南 > 深蹲"
        assert "保持核心稳定。\n\n膝盖方向与脚尖一致。" == entries[0]["content"]
        assert entries[0]["embedding_text"].startswith(
            "健身基础动作指南 > 深蹲\n"
        )


class TestMemoryRetriever:
    @pytest.fixture
    def mock_encoder(self):
        """Create a mock encoder that returns fixed-dimension vectors."""
        mock = MagicMock()
        def fake_encode(texts, normalize_embeddings=False):
            if isinstance(texts, str):
                texts = [texts]
            vecs = np.zeros((len(texts), 384), dtype=np.float32)
            for i, t in enumerate(texts):
                seed = hash(t) % (2**31)
                rng = np.random.RandomState(seed)
                vecs[i] = rng.rand(384).astype(np.float32)
            if normalize_embeddings:
                norms = np.linalg.norm(vecs, axis=1, keepdims=True)
                norms[norms < 1e-8] = 1.0
                vecs = vecs / norms
            return vecs
        mock.encode = fake_encode
        return mock

    @pytest.fixture
    def retriever(self, mock_encoder):
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=mock_encoder,
        ):
            r = MemoryRetriever(embedding_model="mock-model")
            # Bypass lazy loading
            r._encoder = mock_encoder
            return r

    @pytest.fixture
    def sample_docs(self):
        return [
            "Squat is an effective lower body exercise targeting quads and glutes.",
            "During cutting, reduce carb intake and increase protein ratio.",
            "Keep your back straight during deadlifts to avoid injury.",
        ]

    def test_add_and_search(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        result = retriever.search("how to squat", top_k=2, threshold=0.0)
        assert result.ok
        assert len(result.data) >= 1
        assert all("content" in r for r in result.data)

    def test_failed_encoder_load_is_not_retried_for_every_search(self, sample_docs):
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=OSError("model unavailable"),
        ) as loader:
            retriever = MemoryRetriever(embedding_model="missing-model")
            retriever.add_documents(sample_docs)
            first = retriever.search("squat", top_k=2, threshold=0.0)
            second = retriever.search("deadlift", top_k=2, threshold=0.0)

        assert first.ok and first.meta["mode"] == "keyword"
        assert second.ok and second.meta["mode"] == "keyword"
        assert first.meta["embedding_model"] == "missing-model"
        assert "model unavailable" in first.meta["fallback_reason"]
        assert loader.call_count == 1

    def test_search_returns_scores(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        result = retriever.search("diet and nutrition", top_k=3)
        assert result.ok
        for r in result.data:
            assert "score" in r
            assert "content" in r
            assert 0.0 <= r["score"] <= 1.0

    def test_search_with_threshold(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        result = retriever.search("yoga meditation", top_k=3, threshold=0.99)
        assert result.ok
        assert len(result.data) <= 1

    def test_search_can_skip_score_threshold(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)

        result = retriever.search("yoga meditation", top_k=3, threshold=None)

        assert result.ok
        assert len(result.data) == 3

    def test_clear(self, retriever, sample_docs):
        retriever.add_documents(sample_docs)
        retriever.clear()
        result = retriever.search("squat", top_k=5)
        assert result.ok
        assert len(result.data) == 0

    def test_document_count(self, retriever, sample_docs):
        assert retriever.document_count == 0
        retriever.add_documents(sample_docs)
        assert retriever.document_count >= 1

    def test_add_documents_returns_manifest_with_versioned_chunk_ids(
        self,
        retriever,
    ):
        result = retriever.add_documents(
            ["深蹲训练需要保持核心稳定。"],
            sources=["fitness.txt"],
        )
        expected_entries = _build_chunk_entries(
            ["深蹲训练需要保持核心稳定。"],
            ["fitness.txt"],
        )

        assert result.ok
        assert result.data["manifest"]["chunk_count"] == 1
        assert result.data["manifest"]["sources"][0]["source"] == "fitness.txt"
        assert result.data["manifest"]["sources"][0]["chunk_ids"] == [
            expected_entries[0]["id"]
        ]

    def test_search_returns_section_path(self, retriever):
        retriever.add_documents(
            ["# 动作指南\n\n## 深蹲\n保持核心稳定。"],
            sources=["fitness.txt"],
        )

        result = retriever.search("深蹲", top_k=1, threshold=0.0)

        assert result.ok
        assert result.data[0]["section_path"] == "动作指南 > 深蹲"

    def test_reingesting_same_source_replaces_stale_chunks(self, retriever):
        first = retriever.add_documents(
            ["深蹲" * 300],
            sources=["fitness.txt"],
        )
        second = retriever.add_documents(
            ["深蹲" * 10],
            sources=["fitness.txt"],
        )

        assert first.ok
        assert second.ok
        assert second.data["removed"] >= 1
        assert retriever.document_count == 1
        assert retriever._documents == ["深蹲" * 10]


class TestParentChildChunking:
    """Parent-child (small-to-big) chunking contract."""

    def test_child_chunks_are_smaller_than_max(self):
        from unittest.mock import patch

        text = (
            "# 训练原则\n\n"
            "## 深蹲\n"
            "深蹲时保持核心稳定。膝盖沿脚尖方向移动。\n\n"
            "## 硬拉\n"
            "硬拉需要腰背挺直，杠铃沿小腿附近垂直移动。"
        )
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = True
            cfg.retriever_child_chunk_chars = 30
            cfg.retriever_child_chunk_overlap_chars = 5
            cfg.retriever_chunk_chars = 500
            cfg.retriever_chunk_overlap_chars = 80
            cfg.retriever_knowledge_version = "v2"

            entries = _build_chunk_entries([text], ["guide.md"])

        # Each child chunk must stay within the child limit.
        assert all(
            len(e["content"]) <= 30 for e in entries
        ), f"child chunks exceed limit: {[len(e['content']) for e in entries]}"
        # Multiple children expected when text is longer than child_chunk_chars.
        assert len(entries) >= 2

    def test_children_from_same_parent_share_parent_section_id(self):
        from unittest.mock import patch

        text = (
            "# 训练\n\n"
            "## 第一个主题\n"
            "这里是一些内容，句子数量足够多，会被切分为多个子 chunk。"
            "继续增加内容，使得切分后的子 chunk 数量超过一个。"
        )
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = True
            cfg.retriever_child_chunk_chars = 20
            cfg.retriever_child_chunk_overlap_chars = 2
            cfg.retriever_chunk_chars = 500
            cfg.retriever_chunk_overlap_chars = 80
            cfg.retriever_knowledge_version = "v2"

            entries = _build_chunk_entries([text], ["guide.md"])

        pids = [e.get("parent_section_id") for e in entries]
        # All child chunks under the same section share one parent id.
        assert len(set(pids)) == 1, f"expected 1 parent, got {set(pids)}"
        # Each entry carries the full parent_content.
        for e in entries:
            # parent_content is the full section, longer than any single child
            assert len(e["parent_content"]) > len(e["content"])

    def test_h3_leaf_sections_under_same_h2_share_aggregated_parent(self):
        from unittest.mock import patch

        text = (
            "# 动作指南\n\n"
            "## 深蹲\n"
            "### 动作要领\n保持核心稳定，膝盖沿脚尖方向移动。\n\n"
            "### 常见错误\n避免膝盖内扣，也不要弓背。"
        )
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = True
            cfg.retriever_child_chunk_chars = 40
            cfg.retriever_child_chunk_overlap_chars = 5
            cfg.retriever_chunk_chars = 500
            cfg.retriever_chunk_overlap_chars = 80
            cfg.retriever_knowledge_version = "v3-hierarchical"

            entries = _build_chunk_entries([text], ["guide.md"])

        assert len({entry["parent_section_id"] for entry in entries}) == 1
        assert {entry["section_path"] for entry in entries} == {
            "动作指南 > 深蹲 > 动作要领",
            "动作指南 > 深蹲 > 常见错误",
        }
        parent_content = entries[0]["parent_content"]
        assert "### 动作要领" in parent_content
        assert "### 常见错误" in parent_content

    def test_different_h2_topics_never_share_parent(self):
        from unittest.mock import patch

        text = (
            "# 动作指南\n\n"
            "## 深蹲\n### 动作要领\n保持核心稳定。\n\n"
            "## 硬拉\n### 动作要领\n保持腰背中立。"
        )
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = True
            cfg.retriever_child_chunk_chars = 40
            cfg.retriever_child_chunk_overlap_chars = 5
            cfg.retriever_chunk_chars = 500
            cfg.retriever_chunk_overlap_chars = 80
            cfg.retriever_knowledge_version = "v3-hierarchical"

            entries = _build_chunk_entries([text], ["guide.md"])

        parent_by_topic = {
            entry["section_path"].split(" > ")[1]: entry["parent_section_id"]
            for entry in entries
        }
        assert parent_by_topic["深蹲"] != parent_by_topic["硬拉"]

    def test_safety_heading_is_an_independent_parent_boundary(self):
        from unittest.mock import patch

        text = (
            "# 动作指南\n\n"
            "## 深蹲\n"
            "### 动作要领\n保持核心稳定。\n\n"
            "### 安全警示\n膝关节锐痛时停止训练并就医。"
        )
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = True
            cfg.retriever_child_chunk_chars = 50
            cfg.retriever_child_chunk_overlap_chars = 5
            cfg.retriever_chunk_chars = 500
            cfg.retriever_chunk_overlap_chars = 80
            cfg.retriever_knowledge_version = "v3-hierarchical"

            entries = _build_chunk_entries([text], ["guide.md"])

        parent_by_path = {
            entry["section_path"]: entry["parent_section_id"] for entry in entries
        }
        assert parent_by_path["动作指南 > 深蹲 > 动作要领"] != (
            parent_by_path["动作指南 > 深蹲 > 安全警示"]
        )

    def test_standalone_source_section_is_skipped_but_related_topic_remains(self):
        from unittest.mock import patch

        text = (
            "# 健身知识\n\n"
            "## 训练原则\n循序渐进增加训练量。\n\n"
            "## 来源\nhttps://example.com/reference\n\n"
            "## 来源与适用范围\n适用于无明显伤病的普通训练者。"
        )
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = True
            cfg.retriever_child_chunk_chars = 80
            cfg.retriever_child_chunk_overlap_chars = 5
            cfg.retriever_chunk_chars = 500
            cfg.retriever_chunk_overlap_chars = 80
            cfg.retriever_knowledge_version = "v3-hierarchical"

            entries = _build_chunk_entries([text], ["guide.md"])

        contents = "\n".join(entry["content"] for entry in entries)
        paths = {entry["section_path"] for entry in entries}
        assert "example.com" not in contents
        assert "健身知识 > 来源与适用范围" in paths

    def test_long_topic_uses_distinct_bounded_parent_blocks(self):
        from unittest.mock import patch

        text = (
            "# 动作指南\n\n"
            "## 深蹲\n"
            "### 动作要领\n" + "保持核心稳定并控制下蹲速度。" * 12
        )
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = True
            cfg.retriever_child_chunk_chars = 40
            cfg.retriever_child_chunk_overlap_chars = 5
            cfg.retriever_chunk_chars = 90
            cfg.retriever_chunk_overlap_chars = 10
            cfg.retriever_knowledge_version = "v3-hierarchical"

            entries = _build_chunk_entries([text], ["guide.md"])

        parents = {
            entry["parent_section_id"]: entry["parent_content"] for entry in entries
        }
        assert len(parents) > 1
        assert len(parents) == len(set(parents))
        assert all(len(content) <= 90 for content in parents.values())

    def test_disabled_parent_child_falls_back_to_legacy(self):
        from unittest.mock import patch

        text = "# 动作\n\n## 深蹲\n保持核心稳定。"
        with patch("app.tools.retriever.config") as cfg:
            cfg.retriever_parent_child_enabled = False
            cfg.retriever_chunk_chars = 500
            cfg.retriever_chunk_overlap_chars = 80
            cfg.retriever_knowledge_version = "v2"

            entries = _build_chunk_entries([text], ["guide.md"])

        # Legacy: one entry per section, no parent fields.
        assert len(entries) == 1
        assert "parent_section_id" not in entries[0]
        assert "parent_content" not in entries[0]
        assert "保持核心稳定" in entries[0]["content"]

    def test_resolve_parent_results_collapses_siblings(self):
        """_resolve_parent_results deduplicates and swaps in parent content."""
        parent_texts = {
            1: "完整的父文档内容，比单个子 chunk 长得多。包含更多上下文信息。",
            2: "另一个父文档，包含不同的主题内容。",
        }
        children = [
            {"content": "子片段A", "score": 0.9, "parent_section_id": 1,
             "source": "f.txt", "section_path": "A > B"},
            {"content": "子片段B", "score": 0.7, "parent_section_id": 1,
             "source": "f.txt", "section_path": "A > B"},
            {"content": "子片段C", "score": 0.5, "parent_section_id": 2,
             "source": "f.txt", "section_path": "C"},
        ]
        resolved = _resolve_parent_results(children, parent_texts)

        # Two unique parents → two results.
        assert len(resolved) == 2
        assert resolved[0]["content"] == parent_texts[1]
        assert resolved[0]["child_content"] == "子片段A"
        assert resolved[0]["score"] == 0.9  # keeps first-seen score
        assert resolved[0]["parent_collapsed"] == 1  # sibling count
        assert resolved[1]["content"] == parent_texts[2]

    def test_resolve_parent_skips_when_parent_not_found(self):
        """Children without a matching parent_texts entry pass through."""
        children = [
            {"content": "独立内容", "score": 0.8, "parent_section_id": 999,
             "source": "f.txt", "section_path": "X"},
        ]
        resolved = _resolve_parent_results(children, {})
        assert len(resolved) == 1
        assert resolved[0]["content"] == "独立内容"
        assert "child_content" not in resolved[0]

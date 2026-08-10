"""健身知识检索模块：SQLite 持久化、FAISS Dense 检索与 BM25 融合.

PERMISSION: This tool retrieves pre-loaded knowledge content only.
It does NOT perform fact-checking, verify medical claims, or access
external data sources. Retrieved content may be outdated or incomplete.
Users should consult professionals for medical or training decisions.
"""

import hashlib
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_KNOWLEDGE_DB_PATH, config
from app.tools.types import (
    ToolResult,
    ErrorCode,
    check_int_range,
    check_float_range,
)

logger = logging.getLogger(__name__)

# --- Constants ---
TOP_K_MIN = 1
TOP_K_MAX = 100
THRESHOLD_MIN = 0.0
THRESHOLD_MAX = 1.0


def _bm25_dependencies():
    """Load optional lexical-retrieval dependencies with an actionable error."""
    try:
        import jieba
        from rank_bm25 import BM25Okapi
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "BM25 retrieval requires 'jieba' and 'rank-bm25'; "
            "install the project requirements before using hybrid retrieval"
        ) from exc
    return jieba, BM25Okapi


_EXACT_TOKEN_PATTERN = re.compile(
    r"[a-zA-Z]+(?:\d+)?|"
    r"\d+(?:[.\-–~～]\d+)*(?:\s*(?:g/kg|kg|g|mg|ml|kcal|千卡|分钟|秒|次|组|%))?",
    re.IGNORECASE,
)


def _tokenize_for_bm25(text: str) -> List[str]:
    """Tokenize Chinese text while preserving terms such as RPE and 150-300分钟."""
    jieba, _ = _bm25_dependencies()
    normalized = str(text or "").lower().strip()
    tokens = [
        token.strip()
        for token in jieba.lcut(normalized, cut_all=False)
        if token.strip() and re.search(r"[\w\u4e00-\u9fff%]", token)
    ]
    for exact in _EXACT_TOKEN_PATTERN.findall(normalized):
        exact = re.sub(r"\s+", "", exact.lower())
        if exact and exact not in tokens:
            tokens.append(exact)
    return tokens


class MemoryRetriever:
    """基于内存的向量检索器.

    使用 Sentence-Transformer 编码文本,NumPy 存储向量,
    余弦相似度检索 + 可选阈值过滤 + 去重排序后处理.

    Input:
        search(query: str, top_k: int=5, threshold: Optional[float]=0.3)
        传入 ``None`` 可为排名融合保留完整候选预算.

    Output:
        ToolResult.data = [{"content": str, "score": float, "index": int}, ...]
        ToolResult.meta = {"mode": "embedding" | "keyword", "total_docs": int}
    """

    def __init__(
        self,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        device: str = "cpu",
    ):
        self.embedding_model_name = embedding_model
        self.device = device
        self._encoder = None
        self._encoder_load_attempted = False
        self._encoder_error = ""
        self._documents: List[str] = []
        self._sources: List[str] = []
        self._section_paths: List[str] = []
        self._chunk_ids: List[int] = []
        self._source_latest_ids: Dict[str, List[int]] = {}
        self._embeddings: Optional[np.ndarray] = None
        self._parent_texts: Dict[int, str] = {}
        self._parent_section_ids: List[int] = []

    def _ensure_encoder(self):
        """延迟加载 Sentence-Transformer 编码器."""
        if self._encoder is not None or self._encoder_load_attempted:
            return

        self._encoder_load_attempted = True
        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        try:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(
                self.embedding_model_name, device=self.device
            )
        except Exception as e:
            self._encoder_error = str(e)[:500]
            logger.warning(
                f"Cannot load embedding model '{self.embedding_model_name}': {e}. "
                f"Falling back to keyword-based matching."
            )
            self._encoder = None

    def _keyword_search(
        self, query: str, top_k: int = 5
    ) -> List[Dict]:
        """关键词匹配降级：当 embedding 模型不可用时使用.

        同时支持英文（按空格分词）和中文（子串匹配 + 字重叠）。
        """
        results = []
        query_lower = query.lower()
        doc_lower_list = [doc.lower() for doc in self._documents]

        # 方法1: 空格分词匹配（适用于英文）
        query_words = set(query_lower.split())
        if query_words:
            for idx, doc_lower in enumerate(doc_lower_list):
                doc_words = set(doc_lower.split())
                overlap = len(query_words & doc_words)
                if overlap > 0:
                    score = min(overlap / max(len(query_words), 1), 1.0)
                    item = {
                        "content": self._documents[idx],
                        "score": score,
                        "index": self._chunk_ids[idx],
                        "source": self._sources[idx],
                        "section_path": self._section_paths[idx],
                    }
                    if idx < len(self._parent_section_ids):
                        pid = self._parent_section_ids[idx]
                        item["parent_section_id"] = pid
                    results.append(item)

        # 方法2: 子串匹配 + 字重叠（适用于中文等无空格语言）
        # 当查询是纯中文（无空格）或方法1无结果时有效
        if not results or not any(c in query_lower for c in ' '):
            for idx, doc_lower in enumerate(doc_lower_list):
                # 检查完整查询子串是否出现
                substring_score = 0.0
                if query_lower in doc_lower:
                    substring_score = 1.0
                else:
                    # 逐字检查查询的每个字是否在文档中出现
                    query_chars = set(query_lower.replace(' ', ''))
                    if query_chars:
                        doc_chars = set(doc_lower.replace(' ', ''))
                        char_overlap = len(query_chars & doc_chars)
                        if char_overlap > 0:
                            substring_score = char_overlap / len(query_chars) * 0.8

                if substring_score > 0:
                    # 不重复添加已在方法1中的结果
                    existing = [
                        r for r in results if r["index"] == self._chunk_ids[idx]
                    ]
                    if not existing:
                        item = {
                            "content": self._documents[idx],
                            "score": substring_score,
                            "index": self._chunk_ids[idx],
                            "source": self._sources[idx],
                            "section_path": self._section_paths[idx],
                        }
                        if idx < len(self._parent_section_ids):
                            item["parent_section_id"] = (
                                self._parent_section_ids[idx]
                            )
                        results.append(item)

        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:top_k]
        if self._parent_texts:
            results = _resolve_parent_results(results, self._parent_texts)
        return results

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def _remove_chunk_ids(self, ids_to_remove: Sequence[int]) -> int:
        remove_set = set(ids_to_remove)
        if not remove_set:
            return 0
        keep_indices = [
            index
            for index, chunk_id in enumerate(self._chunk_ids)
            if chunk_id not in remove_set
        ]
        removed = len(self._chunk_ids) - len(keep_indices)
        if removed <= 0:
            return 0
        self._documents = [self._documents[index] for index in keep_indices]
        self._sources = [self._sources[index] for index in keep_indices]
        self._section_paths = [self._section_paths[index] for index in keep_indices]
        self._chunk_ids = [self._chunk_ids[index] for index in keep_indices]
        if self._parent_section_ids:
            self._parent_section_ids = [
                self._parent_section_ids[index] for index in keep_indices
            ]
        if self._embeddings is not None:
            self._embeddings = self._embeddings[keep_indices]
        # Rebuild parent_texts to drop entries that no longer have children.
        if self._parent_texts:
            remaining_pids = set(self._parent_section_ids)
            self._parent_texts = {
                pid: text
                for pid, text in self._parent_texts.items()
                if pid in remaining_pids
            }
        return removed

    def add_documents(
        self,
        docs: List[str],
        sources: Optional[Sequence[str]] = None,
    ) -> ToolResult:
        """Add documents to the in-memory store after sentence-aware chunking."""
        self._ensure_encoder()
        normalized_sources = list(sources or [])
        entries = _build_chunk_entries(docs, normalized_sources)
        chunks = [entry["content"] for entry in entries]
        embedding_texts = [entry["embedding_text"] for entry in entries]
        chunk_sources = [entry["source"] for entry in entries]
        section_paths = [entry["section_path"] for entry in entries]
        if not chunks:
            return ToolResult.ok(data={"upserted": 0}, backend="memory")
        incoming_ids = [int(entry["id"]) for entry in entries]
        removed = self._remove_chunk_ids(incoming_ids)
        source_groups: Dict[str, List[int]] = {}
        for entry in entries:
            source = str(entry["source"])
            if source:
                source_groups.setdefault(source, []).append(int(entry["id"]))
        stale_removed = 0
        for source, new_ids in source_groups.items():
            stale_ids = [
                chunk_id
                for chunk_id in self._source_latest_ids.get(source, [])
                if chunk_id not in set(new_ids)
            ]
            stale_removed += self._remove_chunk_ids(stale_ids)
            self._source_latest_ids[source] = list(new_ids)
        parent_section_ids = [
            entry.get("parent_section_id", 0) for entry in entries
        ]
        self._documents.extend(chunks)
        self._sources.extend(chunk_sources)
        self._section_paths.extend(section_paths)
        self._chunk_ids.extend(incoming_ids)
        self._parent_section_ids.extend(parent_section_ids)
        for entry in entries:
            if "parent_section_id" in entry and "parent_content" in entry:
                pid = int(entry["parent_section_id"])
                self._parent_texts.setdefault(pid, str(entry["parent_content"]))
        if self._encoder is not None:
            new_embeddings = self._encoder.encode(
                embedding_texts,
                normalize_embeddings=True,
            )
            if self._embeddings is None:
                self._embeddings = new_embeddings
            else:
                self._embeddings = np.vstack([self._embeddings, new_embeddings])
        logger.info(f"Added {len(chunks)} chunks, total: {len(self._documents)}")
        return ToolResult.ok(
            data={
                "upserted": len(chunks),
                "removed": removed + stale_removed,
                "manifest": _manifest_from_entries(entries),
            },
            backend="memory",
            total_docs=len(self._documents),
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: Optional[float] = 0.3,
    ) -> ToolResult:
        """检索与query最相关的文档片段.

        Returns:
            ToolResult.data = [{"content": str, "score": float, "index": int}, ...]
            按相似度降序排列.
            ToolResult.meta = {"mode": "embedding"|"keyword", "total_docs": int}
        """
        # --- Input validation ---
        if not isinstance(query, str) or not query.strip():
            return ToolResult(
                ok=True,  # empty query → empty results, not an error
                data=[],
                meta={"mode": "keyword", "total_docs": len(self._documents),
                      "note": "Empty query"},
            )
        err = check_int_range(top_k, "top_k", TOP_K_MIN, TOP_K_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        if threshold is not None:
            err = check_float_range(
                threshold, "threshold", THRESHOLD_MIN, THRESHOLD_MAX
            )
            if err:
                return ToolResult.fail(ErrorCode.INVALID_PARAM, err)

        self._ensure_encoder()
        if len(self._documents) == 0:
            return ToolResult.ok(
                data=[],
                mode="keyword",
                total_docs=0,
                note="Knowledge base is empty",
            )

        # 降级：embedding模型不可用时用关键词匹配
        if self._encoder is None:
            results = self._keyword_search(query, top_k)
            return ToolResult.ok(
                data=results,
                mode="keyword",
                total_docs=len(self._documents),
                note="Embedding model unavailable, using keyword matching",
                embedding_model=self.embedding_model_name,
                fallback_reason=self._encoder_error,
            )

        if self._embeddings is None:
            return ToolResult.ok(
                data=[],
                mode="embedding",
                total_docs=len(self._documents),
                note="Documents loaded but not yet embedded",
            )

        query_vec = self._encoder.encode(
            [query], normalize_embeddings=True
        )
        # 余弦相似度 (向量已归一化,点积即余弦)
        scores = np.dot(self._embeddings, query_vec.T).flatten()

        # 可选阈值过滤 → 索引排序 → 取 top_k；Hybrid 传 None 保留完整候选预算。
        qualified = (
            np.arange(len(scores))
            if threshold is None
            else np.where(scores >= threshold)[0]
        )
        sorted_idx = qualified[np.argsort(scores[qualified])[::-1]]
        top_idx = sorted_idx[:top_k]

        # 去重(基于内容)
        seen = set()
        results = []
        for idx in top_idx:
            content = self._documents[int(idx)]
            normalized = content.strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            item = {
                "content": content,
                "score": float(scores[int(idx)]),
                "index": int(self._chunk_ids[int(idx)]),
                "source": self._sources[int(idx)],
                "section_path": self._section_paths[int(idx)],
            }
            if int(idx) < len(self._parent_section_ids):
                pid = self._parent_section_ids[int(idx)]
                if pid:
                    item["parent_section_id"] = pid
            results.append(item)
        if self._parent_texts:
            results = _resolve_parent_results(results, self._parent_texts)
        return ToolResult.ok(
            data=results,
            mode="embedding",
            total_docs=len(self._documents),
            embedding_model=self.embedding_model_name,
        )

    def clear(self) -> ToolResult:
        """清空全部文档和向量."""
        self._documents = []
        self._sources = []
        self._section_paths = []
        self._chunk_ids = []
        self._source_latest_ids = {}
        self._embeddings = None
        self._parent_texts = {}
        self._parent_section_ids = []
        return ToolResult.ok(data={"cleared": True}, backend="memory")


def _split_long_segment(
    segment: str,
    max_chunk_chars: int,
    overlap_chars: int = 0,
) -> List[str]:
    """Split one overlong sentence into bounded windows."""
    if len(segment) <= max_chunk_chars:
        return [segment]
    safe_overlap = max(0, min(overlap_chars, max_chunk_chars - 1))
    step = max_chunk_chars - safe_overlap
    return [
        segment[start : start + max_chunk_chars]
        for start in range(0, len(segment), step)
        if segment[start : start + max_chunk_chars]
    ]


def _overlap_tail(text: str, overlap_chars: int) -> str:
    """Return a bounded tail, preferring the start of a complete sentence."""
    if overlap_chars <= 0 or not text:
        return ""
    window = text[-overlap_chars:]
    boundary = re.search(r"[。！？.!?]\s*", window)
    if boundary and boundary.end() < len(window):
        return window[boundary.end():].lstrip()
    return window


def _chinese_sentence_split(
    text: str,
    max_chunk_chars: int = 500,
    overlap_chars: int = 0,
) -> List[str]:
    """Pack paragraphs and sentences into bounded chunks with real overlap."""
    max_chunk_chars = max(1, int(max_chunk_chars))
    overlap_chars = max(
        0,
        min(int(overlap_chars), max_chunk_chars - 1),
    )
    if not text:
        return [text]

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
        if paragraph.strip()
    ]
    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？.!?])\s*", paragraph)
            if sentence.strip()
        ]
        for sentence_index, sentence in enumerate(sentences):
            separator = ""
            if current:
                separator = "\n\n" if sentence_index == 0 else " "

            if len(sentence) > max_chunk_chars:
                if current:
                    chunks.append(current)
                    current = ""
                long_chunks = _split_long_segment(
                    sentence,
                    max_chunk_chars,
                    overlap_chars,
                )
                chunks.extend(long_chunks)
                continue

            candidate = f"{current}{separator}{sentence}"
            if len(candidate) <= max_chunk_chars:
                current = candidate
                continue

            if current:
                chunks.append(current)
            tail = _overlap_tail(current, overlap_chars)
            separator = "\n\n" if tail and sentence_index == 0 else (" " if tail else "")
            available_for_tail = max_chunk_chars - len(separator) - len(sentence)
            if available_for_tail <= 0:
                tail = ""
                separator = ""
            elif len(tail) > available_for_tail:
                tail = tail[-available_for_tail:]
            current = f"{tail}{separator}{sentence}"
    if current:
        chunks.append(current)
    return chunks or [text]


def _structured_text_split(
    text: str,
    max_chunk_chars: int = 500,
    overlap_chars: int = 0,
) -> List[Dict[str, str]]:
    """Split Markdown-like knowledge while retaining its heading hierarchy."""
    heading_stack: List[tuple[int, str]] = []
    sections: List[Dict[str, Any]] = []
    paragraph_lines: List[str] = []
    paragraphs: List[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            paragraphs.append("\n".join(paragraph_lines).strip())
            paragraph_lines.clear()

    def flush_section() -> None:
        flush_paragraph()
        if not paragraphs:
            return
        sections.append(
            {
                "section_path": " > ".join(title for _, title in heading_stack),
                "content": "\n\n".join(paragraphs),
            }
        )
        paragraphs.clear()

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        heading_match = re.match(r"^(#{1,6})[ \t]+(.+?)\s*$", line)
        if heading_match:
            title = heading_match.group(2).strip()
            if re.match(r"^来源\s*[:：]", title, flags=re.IGNORECASE):
                continue
            flush_section()
            level = len(heading_match.group(1))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue
        if not line:
            flush_paragraph()
            continue
        paragraph_lines.append(line)

    flush_section()
    if not sections and text.strip():
        sections.append({"section_path": "", "content": text.strip()})

    chunks: List[Dict[str, str]] = []
    for section in sections:
        for content in _chinese_sentence_split(
            str(section["content"]),
            max_chunk_chars=max_chunk_chars,
            overlap_chars=overlap_chars,
        ):
            if content.strip():
                chunks.append(
                    {
                        "content": content,
                        "section_path": str(section["section_path"]),
                    }
                )
    return chunks


_INLINE_METADATA_HEADING = re.compile(
    r"^(?:来源|参考来源|核验日期)\s*[:：]",
    flags=re.IGNORECASE,
)
_REFERENCE_SECTION_HEADING = re.compile(
    r"^(?:来源|参考来源)\s*$",
    flags=re.IGNORECASE,
)
_HARD_BOUNDARY_TERMS = (
    "安全",
    "禁忌",
    "警示",
    "风险",
    "就医",
    "转介",
    "注意",
    "重要提示",
    "边界",
)


def _parse_hierarchical_sections(text: str) -> List[Dict[str, Any]]:
    """Parse Markdown into leaf sections without losing heading ancestry.

    Inline source/verification headings are metadata and do not replace the
    document title. A standalone ``## 来源`` section is skipped together with
    its body, while headings such as ``来源与适用范围`` remain searchable.
    """
    heading_stack: List[tuple[int, str]] = []
    sections: List[Dict[str, Any]] = []
    content_lines: List[str] = []
    skipped_reference_level: Optional[int] = None

    def flush_section() -> None:
        content = "\n".join(content_lines).strip()
        if content:
            sections.append(
                {
                    "heading_stack": list(heading_stack),
                    "section_path": " > ".join(
                        title for _, title in heading_stack
                    ),
                    "content": content,
                }
            )
        content_lines.clear()

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        heading_match = re.match(r"^(#{1,6})[ \t]+(.+?)\s*$", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            if skipped_reference_level is not None:
                if level > skipped_reference_level:
                    continue
                skipped_reference_level = None

            if _INLINE_METADATA_HEADING.match(title):
                continue

            flush_section()
            if _REFERENCE_SECTION_HEADING.match(title):
                skipped_reference_level = level
                continue

            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue

        if skipped_reference_level is not None:
            continue
        content_lines.append(raw_line.rstrip())

    flush_section()
    return sections


def _parent_topic_path(heading_stack: Sequence[tuple[int, str]]) -> str:
    """Choose the deterministic parent boundary for one leaf section.

    H2 is the normal topic boundary. Deeper safety/risk headings are isolated
    so warnings are not blended with ordinary advice in the returned context.
    """
    if not heading_stack:
        return ""

    h2_index = next(
        (index for index, (level, _) in enumerate(heading_stack) if level == 2),
        None,
    )
    boundary_index = h2_index if h2_index is not None else 0
    search_start = boundary_index + 1
    for index in range(search_start, len(heading_stack)):
        level, title = heading_stack[index]
        if level >= 3 and any(term in title for term in _HARD_BOUNDARY_TERMS):
            boundary_index = index
            break
    return " > ".join(title for _, title in heading_stack[: boundary_index + 1])


def _render_parent_unit(
    heading_stack: Sequence[tuple[int, str]],
    content: str,
) -> str:
    """Keep a leaf heading visible when several leaves share one parent."""
    if not heading_stack:
        return content
    level, title = heading_stack[-1]
    return f"{'#' * level} {title}\n{content}"


def _hierarchical_parent_split(
    text: str,
    max_parent_chars: int = 500,
    overlap_chars: int = 0,
) -> List[Dict[str, Any]]:
    """Aggregate leaf sections into H2-scoped parent blocks.

    Retrieval children retain their most specific heading path. Returned
    parents combine adjacent H3/paragraph units under the same H2, bounded by
    ``max_parent_chars``. Different H2 topics and safety boundaries never mix.
    """
    max_parent_chars = max(1, int(max_parent_chars))
    leaf_sections = _parse_hierarchical_sections(text)
    parents: List[Dict[str, Any]] = []
    active_path: Optional[str] = None
    active_sections: List[Dict[str, Any]] = []

    def emit_active_group() -> None:
        nonlocal active_sections
        if not active_sections:
            return

        rendered_parts: List[str] = []
        child_sections: List[Dict[str, str]] = []

        def emit_parent() -> None:
            if not rendered_parts:
                return
            parents.append(
                {
                    "content": "\n\n".join(rendered_parts),
                    "section_path": active_path or "",
                    "child_sections": list(child_sections),
                    "parent_block_index": len(parents),
                }
            )
            rendered_parts.clear()
            child_sections.clear()

        for section in active_sections:
            raw_content = str(section["content"]).strip()
            heading_stack = list(section.get("heading_stack") or [])
            section_path = str(section.get("section_path") or "")
            if not raw_content:
                continue

            heading_prefix = ""
            if heading_stack:
                level, title = heading_stack[-1]
                heading_prefix = f"{'#' * level} {title}\n"
            body_limit = max(1, max_parent_chars - len(heading_prefix))
            body_parts = _chinese_sentence_split(
                raw_content,
                max_chunk_chars=body_limit,
                overlap_chars=min(overlap_chars, max(0, body_limit - 1)),
            )
            for body_part in body_parts:
                body_part = str(body_part).strip()
                if not body_part:
                    continue
                rendered = _render_parent_unit(heading_stack, body_part)
                separator_size = 2 if rendered_parts else 0
                current_size = sum(len(part) for part in rendered_parts)
                current_size += max(0, len(rendered_parts) - 1) * 2
                if rendered_parts and (
                    current_size + separator_size + len(rendered)
                    > max_parent_chars
                ):
                    emit_parent()
                rendered_parts.append(rendered)
                child_sections.append(
                    {"content": body_part, "section_path": section_path}
                )

        emit_parent()
        active_sections = []

    for section in leaf_sections:
        topic_path = _parent_topic_path(section.get("heading_stack") or [])
        if active_path is not None and topic_path != active_path:
            emit_active_group()
        active_path = topic_path
        active_sections.append(section)
    emit_active_group()
    return parents


def _content_hash(content: str) -> str:
    """Build a stable content hash for manifest and chunk identity."""
    return hashlib.blake2b(content.encode("utf-8"), digest_size=16).hexdigest()


def _parent_section_id(
    source: str,
    section_path: str,
    version: str,
    block_identity: str = "",
) -> int:
    """Stable parent section identifier so children from the same section share one key.

    ``block_identity`` distinguishes bounded blocks when one logical H2 topic
    is longer than the parent limit. This avoids collapsing separate blocks
    that happen to share the same source and section path.
    """
    identity = "\x1f".join([version, source, section_path, block_identity])
    digest = hashlib.blake2b(identity.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False) & ((1 << 63) - 1)


def _resolve_parent_results(
    child_results: List[Dict[str, Any]],
    parent_texts: Dict[int, str],
) -> List[Dict[str, Any]]:
    """Collapse child-chunk hits into deduplicated parent-sized results.

    For each child hit we look up ``parent_section_id`` and replace
    ``content`` with the full parent section text.  Hits that share the
    same parent are collapsed: the first-seen (highest-ranked) hit keeps
    its score and metadata; later siblings provide a ``parent_collapsed``
    marker so consumers can inspect the raw child provenance.

    When a parent id is missing from ``parent_texts`` (backward-compat
    with pre-parent-child databases), the child's own content is kept.
    """
    if not child_results:
        return child_results
    seen_parents: Dict[int, int] = {}
    resolved: List[Dict[str, Any]] = []
    for item in child_results:
        pid = item.get("parent_section_id")
        if pid is None or pid not in parent_texts:
            resolved.append(item)
            continue
        if pid in seen_parents:
            resolved[seen_parents[pid]]["parent_collapsed"] = (
                resolved[seen_parents[pid]].get("parent_collapsed", 0) + 1
            )
            continue
        seen_parents[pid] = len(resolved)
        # Keep the child's section_path and score, but replace content with parent.
        resolved.append(
            {
                **item,
                "content": parent_texts[pid],
                "child_content": item.get("content", ""),
            }
        )
    return resolved


def _stable_chunk_id(
    content: str,
    source: str = "",
    chunk_index: Optional[int] = None,
    version: Optional[str] = None,
) -> int:
    """Build a deterministic positive INT64 primary key for a text chunk.

    The default call keeps backward-compatible content-only behavior for tests
    and ad-hoc callers. Retriever ingestion passes source, chunk_index, and
    knowledge version so updated files do not collide with unrelated chunks.
    """
    if not source and chunk_index is None and version is None:
        digest = hashlib.blake2b(content.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=False) & ((1 << 63) - 1)

    identity_parts = [version or "", source or ""]
    if chunk_index is not None:
        identity_parts.append(str(chunk_index))
    identity_parts.append(_content_hash(content))
    identity = "\x1f".join(identity_parts)
    digest = hashlib.blake2b(identity.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False) & ((1 << 63) - 1)


def _build_chunk_entries(
    docs: Sequence[str],
    sources: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Chunk documents and attach versioned identity metadata.

    When ``config.retriever_parent_child_enabled`` is True the pipeline
    operates in parent-child mode:

    * H2 topics are **parents**; adjacent H3/paragraph units are aggregated
      within that topic while safety/risk headings remain isolated.
    * Leaf content is split into smaller **child** chunks with
      ``config.retriever_child_chunk_chars`` / ``overlap_chars`` and retains
      its most specific heading path.
    * Child chunks carry ``parent_section_id`` and ``parent_content`` so
      retrieval can match at fine granularity and return the full parent.

    When the flag is disabled the call is backward-compatible with the
    previous single-level 500-char sentence-packing strategy.
    """
    normalized_sources = list(sources or [])
    entries: List[Dict[str, Any]] = []
    version = str(config.retriever_knowledge_version or "v3-hierarchical")
    parent_child = config.retriever_parent_child_enabled

    for doc_index, doc in enumerate(docs):
        source = (
            str(normalized_sources[doc_index])[:1024]
            if doc_index < len(normalized_sources)
            else ""
        )
        if parent_child:
            structured = _hierarchical_parent_split(
                doc,
                max_parent_chars=config.retriever_chunk_chars,
                overlap_chars=config.retriever_chunk_overlap_chars,
            )
        else:
            structured = _structured_text_split(
                doc,
                max_chunk_chars=config.retriever_chunk_chars,
                overlap_chars=config.retriever_chunk_overlap_chars,
            )
        if not structured:
            continue

        document_child_index = 0
        for section in structured:
            section_content = str(section["content"]).strip()
            section_path = str(section["section_path"])
            if not section_content:
                continue

            if parent_child:
                parent_block_index = int(section.get("parent_block_index", 0))
                block_identity = (
                    f"{parent_block_index}:{_content_hash(section_content)}"
                )
                pid = _parent_section_id(
                    source,
                    section_path,
                    version,
                    block_identity,
                )
                child_sections = section.get("child_sections") or [
                    {"content": section_content, "section_path": section_path}
                ]
                for child_section in child_sections:
                    child_section_path = str(
                        child_section.get("section_path") or section_path
                    )
                    child_chunks = _chinese_sentence_split(
                        str(child_section.get("content") or ""),
                        max_chunk_chars=config.retriever_child_chunk_chars,
                        overlap_chars=config.retriever_child_chunk_overlap_chars,
                    )
                    for child_content in child_chunks:
                        child_text = str(child_content).strip()
                        if not child_text:
                            continue
                        embedding_text = (
                            f"{child_section_path}\n{child_text}"
                            if child_section_path
                            else child_text
                        )
                        entries.append(
                            {
                                "id": _stable_chunk_id(
                                    embedding_text,
                                    source=source,
                                    chunk_index=document_child_index,
                                    version=version,
                                ),
                                "content": child_text,
                                "embedding_text": embedding_text,
                                "source": source,
                                "section_path": child_section_path,
                                "chunk_index": document_child_index,
                                "content_hash": _content_hash(child_text),
                                "version": version,
                                "parent_section_id": pid,
                                "parent_content": section_content,
                            }
                        )
                        document_child_index += 1
            else:
                # Legacy single-level: section content is the chunk.
                embedding_text = (
                    f"{section_path}\n{section_content}"
                    if section_path
                    else section_content
                )
                entries.append(
                    {
                        "id": _stable_chunk_id(
                            embedding_text,
                            source=source,
                            chunk_index=0,
                            version=version,
                        ),
                        "content": section_content,
                        "embedding_text": embedding_text,
                        "source": source,
                        "section_path": section_path,
                        "chunk_index": 0,
                        "content_hash": _content_hash(section_content),
                        "version": version,
                    }
                )
    return entries


def _manifest_from_entries(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a compact ingestion manifest safe to expose in ToolResult."""
    sources: Dict[str, Dict[str, Any]] = {}
    parent_ids: set = set()
    for entry in entries:
        source = str(entry.get("source") or "")
        bucket = sources.setdefault(
            source,
            {
                "source": source,
                "version": entry.get("version", ""),
                "chunk_count": 0,
                "chunk_ids": [],
                "content_hashes": [],
                "section_paths": [],
            },
        )
        bucket["chunk_count"] += 1
        bucket["chunk_ids"].append(int(entry["id"]))
        bucket["content_hashes"].append(str(entry["content_hash"]))
        bucket["section_paths"].append(str(entry.get("section_path") or ""))
        if "parent_section_id" in entry:
            parent_ids.add(int(entry["parent_section_id"]))
    manifest = {
        "version": str(
            config.retriever_knowledge_version or "v3-hierarchical"
        ),
        "source_count": len(sources),
        "chunk_count": len(entries),
        "sources": list(sources.values()),
    }
    if parent_ids:
        manifest["parent_section_count"] = len(parent_ids)
    return manifest


def _vector_store_error_code(exc: Exception) -> str:
    """Classify local vector-store failures into the shared error taxonomy."""
    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return ErrorCode.CONFIG_MISSING
    if isinstance(exc, RuntimeError) and "faiss-cpu" in str(exc):
        return ErrorCode.CONFIG_MISSING
    if isinstance(exc, (sqlite3.Error, OSError)):
        return ErrorCode.INTERNAL_ERROR
    return ErrorCode.INTERNAL_ERROR


class VectorStoreDimensionMismatch(ValueError):
    """Raised when persisted vectors do not match the configured encoder."""

    def __init__(
        self,
        *,
        db_path: str,
        existing_dimension: int,
        expected_dimension: int,
        embedding_model: str,
    ) -> None:
        self.db_path = db_path
        self.existing_dimension = existing_dimension
        self.expected_dimension = expected_dimension
        self.embedding_model = embedding_model
        super().__init__(
            f"SQLite vector store '{db_path}' has vector dimension "
            f"{existing_dimension}, but embedding model '{embedding_model}' returns "
            f"{expected_dimension}. Back up or clear the database, then rebuild the "
            "knowledge index with the configured embedding model."
        )


class EmbeddingModelUnavailable(RuntimeError):
    """Raised when the configured Sentence-Transformer cannot be loaded."""

    def __init__(self, embedding_model: str, reason: str) -> None:
        self.embedding_model = embedding_model
        self.reason = reason[:500]
        super().__init__(
            f"Embedding model '{embedding_model}' could not be loaded: "
            f"{self.reason}. Download/cache the model or set EMBEDDING_MODEL "
            "to an available Sentence-Transformer."
        )


class BM25Retriever:
    """In-memory BM25 index over the same structured chunks as dense retrieval."""

    def __init__(self) -> None:
        self._entries: Dict[int, Dict[str, Any]] = {}
        self._source_latest_ids: Dict[str, List[int]] = {}
        self._ordered_ids: List[int] = []
        self._bm25 = None
        self._parent_texts: Dict[int, str] = {}

    @property
    def document_count(self) -> int:
        return len(self._entries)

    def _rebuild_index(self) -> None:
        _, bm25_class = _bm25_dependencies()
        self._ordered_ids = list(self._entries)
        if not self._ordered_ids:
            self._bm25 = None
            return
        corpus = [
            _tokenize_for_bm25(self._entries[chunk_id]["embedding_text"])
            for chunk_id in self._ordered_ids
        ]
        self._bm25 = bm25_class(corpus)
        # BM25Okapi's epsilon floor can stay negative on a very small corpus.
        # Use the common positive-IDF variant so an exact match never ranks
        # below a document with zero term overlap.
        corpus_size = len(corpus)
        document_frequency: Dict[str, int] = {}
        for tokens in corpus:
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1
        self._bm25.idf = {
            token: float(
                np.log(1.0 + (corpus_size - frequency + 0.5) / (frequency + 0.5))
            )
            for token, frequency in document_frequency.items()
        }
        self._bm25.average_idf = float(
            np.mean(list(self._bm25.idf.values())) if self._bm25.idf else 0.0
        )

    def add_documents(
        self,
        docs: List[str],
        sources: Optional[Sequence[str]] = None,
    ) -> ToolResult:
        """Chunk and index documents; re-ingesting a source removes stale chunks."""
        try:
            _bm25_dependencies()
            entries = _build_chunk_entries(docs, list(sources or []))
            if not entries:
                return ToolResult.ok(
                    data={"upserted": 0, "removed": 0},
                    backend="bm25",
                    total_docs=self.document_count,
                )

            grouped: Dict[str, List[int]] = {}
            for entry in entries:
                source = str(entry.get("source") or "")
                if source:
                    grouped.setdefault(source, []).append(int(entry["id"]))

            removed_ids = set()
            for source, new_ids in grouped.items():
                removed_ids.update(
                    chunk_id
                    for chunk_id in self._source_latest_ids.get(source, [])
                    if chunk_id not in set(new_ids)
                )
                self._source_latest_ids[source] = list(new_ids)
            for chunk_id in removed_ids:
                self._entries.pop(chunk_id, None)

            replaced = sum(
                1 for entry in entries if int(entry["id"]) in self._entries
            )
            for entry in entries:
                self._entries[int(entry["id"])] = dict(entry)
                if "parent_section_id" in entry and "parent_content" in entry:
                    self._parent_texts.setdefault(
                        int(entry["parent_section_id"]),
                        str(entry["parent_content"]),
                    )
            self._rebuild_index()
            return ToolResult.ok(
                data={
                    "upserted": len(entries),
                    "removed": len(removed_ids) + replaced,
                    "manifest": _manifest_from_entries(entries),
                },
                backend="bm25",
                total_docs=self.document_count,
            )
        except RuntimeError as exc:
            return ToolResult.fail(ErrorCode.CONFIG_MISSING, str(exc), backend="bm25")
        except Exception as exc:
            return ToolResult.fail(
                ErrorCode.INTERNAL_ERROR,
                f"BM25 indexing failed: {exc}",
                backend="bm25",
            )

    def search(self, query: str, top_k: int = 20) -> ToolResult:
        """Return positive-scoring BM25 candidates in descending score order."""
        if not isinstance(query, str) or not query.strip():
            return ToolResult.ok(
                data=[], mode="bm25", backend="bm25",
                total_docs=self.document_count, note="Empty query",
            )
        err = check_int_range(top_k, "top_k", TOP_K_MIN, TOP_K_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err, backend="bm25")
        if self._bm25 is None:
            return ToolResult.ok(
                data=[], mode="bm25", backend="bm25",
                total_docs=self.document_count,
                note="Knowledge base is empty",
            )
        try:
            tokens = _tokenize_for_bm25(query)
            if not tokens:
                return ToolResult.ok(
                    data=[], mode="bm25", backend="bm25",
                    total_docs=self.document_count,
                )
            scores = self._bm25.get_scores(tokens)
            ranked = sorted(
                range(len(scores)),
                key=lambda index: (-float(scores[index]), index),
            )
            results = []
            for position in ranked:
                score = float(scores[position])
                if score <= 0:
                    continue
                entry = self._entries[self._ordered_ids[position]]
                item = {
                    "content": entry["content"],
                    "score": score,
                    "index": int(entry["id"]),
                    "source": entry["source"],
                    "section_path": entry["section_path"],
                }
                if "parent_section_id" in entry:
                    item["parent_section_id"] = int(entry["parent_section_id"])
                results.append(item)
                if len(results) >= top_k:
                    break
            if self._parent_texts:
                results = _resolve_parent_results(results, self._parent_texts)
            return ToolResult.ok(
                data=results,
                mode="bm25",
                backend="bm25",
                total_docs=self.document_count,
            )
        except RuntimeError as exc:
            return ToolResult.fail(ErrorCode.CONFIG_MISSING, str(exc), backend="bm25")
        except Exception as exc:
            return ToolResult.fail(
                ErrorCode.INTERNAL_ERROR,
                f"BM25 search failed: {exc}",
                backend="bm25",
            )

    def clear(self) -> ToolResult:
        self._entries = {}
        self._source_latest_ids = {}
        self._ordered_ids = []
        self._bm25 = None
        self._parent_texts = {}
        return ToolResult.ok(data={"cleared": True}, backend="bm25")


class HybridRetriever:
    """Fuse dense and BM25 ranks with RRF while preserving retriever inputs."""

    def __init__(
        self,
        dense_retriever: Any,
        lexical_retriever: Optional[BM25Retriever] = None,
        *,
        candidate_k: int = 20,
        rrf_k: int = 60,
    ) -> None:
        if check_int_range(candidate_k, "candidate_k", TOP_K_MIN, TOP_K_MAX):
            raise ValueError("candidate_k must be between 1 and 100")
        if not isinstance(rrf_k, int) or rrf_k <= 0:
            raise ValueError("rrf_k must be a positive integer")
        self.dense = dense_retriever
        self.lexical = lexical_retriever or BM25Retriever()
        self.candidate_k = candidate_k
        self.rrf_k = rrf_k

    @property
    def document_count(self) -> int:
        return max(
            int(getattr(self.dense, "document_count", 0)),
            self.lexical.document_count,
        )

    def add_documents(
        self,
        docs: List[str],
        sources: Optional[Sequence[str]] = None,
    ) -> ToolResult:
        """Write identical source documents to both routes or expose the failure."""
        normalized_sources = list(sources or [])
        dense_result = self.dense.add_documents(docs, normalized_sources)
        if not dense_result.ok:
            return dense_result
        lexical_result = self.lexical.add_documents(docs, normalized_sources)
        if not lexical_result.ok:
            return lexical_result
        return ToolResult.ok(
            data=lexical_result.data,
            backend="hybrid",
            dense_backend=dense_result.meta.get("backend", "dense"),
            total_docs=self.document_count,
        )

    @staticmethod
    def _dedupe_key(item: Dict[str, Any]) -> tuple:
        return (
            str(item.get("source") or "").strip().lower(),
            re.sub(r"\s+", " ", str(item.get("content") or "")).strip().lower(),
        )

    def _fuse(
        self,
        dense_items: Sequence[Dict[str, Any]],
        lexical_items: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        fused: Dict[tuple, Dict[str, Any]] = {}
        for route, items in (("dense", dense_items), ("bm25", lexical_items)):
            for rank, item in enumerate(items, start=1):
                key = self._dedupe_key(item)
                if not key[1]:
                    continue
                bucket = fused.setdefault(
                    key,
                    {
                        **item,
                        "score": 0.0,
                        "score_type": "rrf",
                        "retrieval_routes": [],
                    },
                )
                bucket["score"] += 1.0 / (self.rrf_k + rank)
                bucket[f"{route}_score"] = float(item.get("score", 0.0))
                bucket[f"{route}_rank"] = rank
                bucket["retrieval_routes"].append(route)
                for field in ("source", "section_path", "index"):
                    if not bucket.get(field) and item.get(field) is not None:
                        bucket[field] = item[field]
        return sorted(
            fused.values(),
            key=lambda item: (
                -float(item["score"]),
                min(item.get("dense_rank", 10**9), item.get("bm25_rank", 10**9)),
                str(item.get("source") or ""),
                str(item.get("content") or ""),
            ),
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> ToolResult:
        """Recall both routes without pre-filtering Dense candidates, then apply RRF."""
        if not isinstance(query, str) or not query.strip():
            return ToolResult.ok(
                data=[], mode="hybrid", fusion="rrf", backend="hybrid",
                total_docs=self.document_count, note="Empty query",
            )
        err = check_int_range(top_k, "top_k", TOP_K_MIN, TOP_K_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err, backend="hybrid")
        err = check_float_range(threshold, "threshold", THRESHOLD_MIN, THRESHOLD_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err, backend="hybrid")

        candidate_k = min(TOP_K_MAX, max(top_k, self.candidate_k))
        # A fixed Dense-score threshold would shrink one route before rank fusion
        # and make its contribution query-dependent. RRF therefore receives the
        # same candidate budget from both routes. ``threshold`` remains in this
        # public signature for compatibility with the shared Retriever interface.
        dense_result = self.dense.search(query, candidate_k, None)
        if not dense_result.ok:
            return dense_result
        lexical_result = self.lexical.search(query, candidate_k)
        if not lexical_result.ok:
            return lexical_result

        dense_mode = str(dense_result.meta.get("mode") or "dense")
        dense_items = [] if dense_mode == "keyword" else list(dense_result.data or [])
        lexical_items = list(lexical_result.data or [])
        ranked = self._fuse(dense_items, lexical_items)
        # Parent-child resolution after RRF so both routes contribute to
        # the fused rank before children of the same parent are collapsed.
        parent_texts: Dict[int, str] = {}
        for retriever in (self.dense, self.lexical):
            pt = getattr(retriever, "_parent_texts", None)
            if pt:
                parent_texts.update(pt)
        parent_texts.update(getattr(self, "_parent_texts", {}))
        if parent_texts:
            ranked = _resolve_parent_results(ranked, parent_texts)
        mode = "hybrid" if dense_items else "bm25"
        return ToolResult.ok(
            data=ranked[:top_k],
            mode=mode,
            backend="hybrid",
            fusion="rrf",
            score_type="rrf",
            rrf_k=self.rrf_k,
            candidate_k=candidate_k,
            dense_candidates=len(dense_items),
            bm25_candidates=len(lexical_items),
            dense_threshold_applied=False,
            dense_mode=dense_mode,
            dense_meta=dict(dense_result.meta),
            total_docs=self.document_count,
        )

    def clear(self) -> ToolResult:
        dense_result = self.dense.clear()
        lexical_result = self.lexical.clear()
        if dense_result.ok and lexical_result.ok:
            return ToolResult.ok(data={"cleared": True}, backend="hybrid")
        return dense_result if not dense_result.ok else lexical_result

    def close(self) -> None:
        if hasattr(self.dense, "close"):
            self.dense.close()


class VectorStoreModelMismatch(ValueError):
    """Raised when persisted vectors were created by another encoder."""

    def __init__(self, db_path: str, stored_model: str, expected_model: str) -> None:
        self.db_path = db_path
        self.stored_model = stored_model
        self.expected_model = expected_model
        super().__init__(
            f"SQLite vector store '{db_path}' was built with embedding model "
            f"'{stored_model}', but the configured model is '{expected_model}'. "
            "Back up or clear the database, then rebuild the knowledge index."
        )


class SQLiteFaissRetriever:
    """Persist chunks and vectors in SQLite, then search them with FAISS.

    Responsibility:
        The class owns one local database, performs idempotent source replacement,
        rebuilds an in-process ``IndexFlatIP`` from persisted normalized vectors,
        and returns cosine-similarity matches with optional score filtering.

    Permission boundary:
        It may create the parent directory and read/write only ``db_path``. SQL is
        static and parameters are bound; callers cannot provide SQL fragments.

    Error contract:
        Public operations return ``ToolResult``. Missing FAISS/embedding packages
        are configuration errors; incompatible persisted vectors are conflicts;
        SQLite and unexpected runtime failures are internal errors.
    """

    backend_name = "sqlite_faiss"

    def __init__(
        self,
        db_path: str = DEFAULT_KNOWLEDGE_DB_PATH,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        device: str = "cpu",
        timeout_seconds: float = 3.0,
        encoder: Optional[Any] = None,
    ) -> None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError("db_path must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        raw_db_path = db_path.strip()
        self.db_path = (
            ":memory:"
            if raw_db_path == ":memory:"
            else str(Path(raw_db_path).expanduser())
        )
        self.embedding_model_name = embedding_model
        self.device = device
        self.timeout_seconds = timeout_seconds
        self._encoder = encoder
        self._connection: Optional[sqlite3.Connection] = None
        self._index = None
        self._index_ready = False
        self._dimension: Optional[int] = None
        self._records_by_id: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._parent_texts: Dict[int, str] = {}

    @staticmethod
    def _load_faiss():
        try:
            import faiss
        except (ImportError, ModuleNotFoundError) as exc:
            raise RuntimeError(
                "SQLite+FAISS retrieval requires 'faiss-cpu'; install the "
                "project requirements before using this backend"
            ) from exc
        return faiss

    def _ensure_encoder(self) -> None:
        if self._encoder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(
                self.embedding_model_name,
                device=self.device,
            )
        except Exception as exc:
            raise EmbeddingModelUnavailable(
                self.embedding_model_name,
                str(exc),
            ) from exc

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        matrix = np.ascontiguousarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] < 1:
            raise ValueError(
                f"Embedding model returned an invalid matrix shape: {matrix.shape}"
            )
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms <= 0):
            raise ValueError("Embedding model returned a zero-length vector")
        return np.ascontiguousarray(matrix / norms, dtype=np.float32)

    def _ensure_connection_locked(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.db_path,
            timeout=self.timeout_seconds,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS vector_store_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                section_path TEXT NOT NULL DEFAULT '',
                chunk_index INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                knowledge_version TEXT NOT NULL,
                embedding BLOB NOT NULL,
                embedding_dim INTEGER NOT NULL,
                parent_section_id INTEGER NOT NULL DEFAULT 0,
                parent_content TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source
                ON knowledge_chunks(source);
            """
        )
        # Migrate older databases that lack parent-child columns.
        connection.execute(
            """
            INSERT OR IGNORE INTO vector_store_meta(key, value)
            VALUES ('schema_parent_child', 'v2')
            """
        )
        existing = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(knowledge_chunks)"
            ).fetchall()
        }
        if "parent_section_id" not in existing:
            connection.execute(
                "ALTER TABLE knowledge_chunks "
                "ADD COLUMN parent_section_id INTEGER NOT NULL DEFAULT 0"
            )
        if "parent_content" not in existing:
            connection.execute(
                "ALTER TABLE knowledge_chunks "
                "ADD COLUMN parent_content TEXT NOT NULL DEFAULT ''"
            )
        connection.commit()
        self._connection = connection
        return connection

    def _metadata_locked(self) -> Dict[str, str]:
        connection = self._ensure_connection_locked()
        return {
            str(row["key"]): str(row["value"])
            for row in connection.execute("SELECT key, value FROM vector_store_meta")
        }

    def _validate_store_locked(self, dimension: int) -> None:
        metadata = self._metadata_locked()
        stored_model = metadata.get("embedding_model")
        if stored_model and stored_model != self.embedding_model_name:
            raise VectorStoreModelMismatch(
                self.db_path,
                stored_model,
                self.embedding_model_name,
            )
        stored_dimension = metadata.get("embedding_dimension")
        if stored_dimension and int(stored_dimension) != dimension:
            raise VectorStoreDimensionMismatch(
                db_path=self.db_path,
                existing_dimension=int(stored_dimension),
                expected_dimension=dimension,
                embedding_model=self.embedding_model_name,
            )

    def _write_metadata_locked(self, dimension: int) -> None:
        connection = self._ensure_connection_locked()
        connection.executemany(
            "INSERT OR REPLACE INTO vector_store_meta(key, value) VALUES (?, ?)",
            [
                ("embedding_model", self.embedding_model_name),
                ("embedding_dimension", str(dimension)),
                ("index_type", "IndexFlatIP"),
            ],
        )

    def _rebuild_index_locked(self) -> None:
        faiss = self._load_faiss()
        connection = self._ensure_connection_locked()
        rows = connection.execute(
            """
            SELECT id, content, source, section_path, chunk_index,
                   embedding, embedding_dim, parent_section_id, parent_content
            FROM knowledge_chunks
            ORDER BY id
            """
        ).fetchall()
        self._records_by_id = {}
        if not rows:
            self._index = None
            self._dimension = None
            self._index_ready = True
            return

        dimensions = {int(row["embedding_dim"]) for row in rows}
        if len(dimensions) != 1:
            raise ValueError("SQLite vector store contains mixed embedding dimensions")
        dimension = dimensions.pop()
        self._validate_store_locked(dimension)
        vectors = []
        ids = []
        for row in rows:
            vector = np.frombuffer(row["embedding"], dtype=np.float32)
            if vector.size != dimension:
                raise ValueError(
                    f"Stored vector {int(row['id'])} has invalid dimension "
                    f"{vector.size}; expected {dimension}"
                )
            vectors.append(vector)
            chunk_id = int(row["id"])
            ids.append(chunk_id)
            self._records_by_id[chunk_id] = {
                "content": str(row["content"]),
                "source": str(row["source"]),
                "section_path": str(row["section_path"]),
                "chunk_index": int(row["chunk_index"]),
                "parent_section_id": int(row["parent_section_id"] or 0),
                "parent_content": str(row["parent_content"] or ""),
            }
        matrix = self._normalize(np.vstack(vectors))
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
        index.add_with_ids(matrix, np.asarray(ids, dtype=np.int64))
        self._index = index
        self._dimension = dimension
        self._index_ready = True
        # Rebuild parent_texts from records for search-time resolution.
        self._parent_texts = {}
        for record in self._records_by_id.values():
            pid = record.get("parent_section_id", 0)
            pcontent = record.get("parent_content", "")
            if pid and pcontent:
                self._parent_texts.setdefault(pid, pcontent)

    def _ensure_index_locked(self) -> None:
        if not self._index_ready:
            self._rebuild_index_locked()

    @property
    def document_count(self) -> int:
        try:
            with self._lock:
                connection = self._ensure_connection_locked()
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM knowledge_chunks"
                ).fetchone()
                return int(row["count"] if row else 0)
        except Exception:
            return 0

    def add_documents(
        self,
        docs: List[str],
        sources: Optional[Sequence[str]] = None,
    ) -> ToolResult:
        """Chunk, encode, and atomically replace documents by source."""
        if not isinstance(docs, list) or any(not isinstance(doc, str) for doc in docs):
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                "docs must be a list of strings",
            )
        entries = _build_chunk_entries(docs, list(sources or []))
        if not entries:
            return ToolResult.ok(
                data={"upserted": 0, "removed": 0},
                backend=self.backend_name,
                db_path=self.db_path,
            )
        try:
            self._load_faiss()
            self._ensure_encoder()
            embeddings = self._normalize(
                np.asarray(
                    self._encoder.encode(
                        [str(entry["embedding_text"]) for entry in entries],
                        normalize_embeddings=True,
                    ),
                    dtype=np.float32,
                )
            )
            if embeddings.shape[0] != len(entries):
                raise ValueError(
                    "Embedding model returned an invalid row count: "
                    f"{embeddings.shape[0]} for {len(entries)} chunks"
                )
            dimension = int(embeddings.shape[1])
            with self._lock:
                connection = self._ensure_connection_locked()
                self._validate_store_locked(dimension)
                incoming_ids = [int(entry["id"]) for entry in entries]
                sources_to_replace = list(
                    dict.fromkeys(
                        str(entry["source"])
                        for entry in entries
                        if str(entry["source"])
                    )
                )
                existing_ids = set()
                for source in sources_to_replace:
                    existing_ids.update(
                        int(row["id"])
                        for row in connection.execute(
                            "SELECT id FROM knowledge_chunks WHERE source = ?",
                            (source,),
                        )
                    )
                if incoming_ids:
                    placeholders = ",".join("?" for _ in incoming_ids)
                    existing_ids.update(
                        int(row["id"])
                        for row in connection.execute(
                            f"SELECT id FROM knowledge_chunks WHERE id IN ({placeholders})",
                            incoming_ids,
                        )
                    )
                with connection:
                    for source in sources_to_replace:
                        connection.execute(
                            "DELETE FROM knowledge_chunks WHERE source = ?",
                            (source,),
                        )
                    connection.executemany(
                        """
                        INSERT OR REPLACE INTO knowledge_chunks(
                            id, content, source, section_path, chunk_index,
                            content_hash, knowledge_version, embedding, embedding_dim,
                            parent_section_id, parent_content
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                int(entry["id"]),
                                str(entry["content"]),
                                str(entry["source"]),
                                str(entry["section_path"]),
                                int(entry["chunk_index"]),
                                str(entry["content_hash"]),
                                str(entry["version"]),
                                embeddings[index].tobytes(),
                                dimension,
                                int(entry.get("parent_section_id", 0)),
                                str(entry.get("parent_content", "")),
                            )
                            for index, entry in enumerate(entries)
                        ],
                    )
                    self._write_metadata_locked(dimension)
                self._index_ready = False
                self._rebuild_index_locked()
            return ToolResult.ok(
                data={
                    "upserted": len(entries),
                    "removed": len(existing_ids),
                    "primary_keys": incoming_ids,
                    "manifest": _manifest_from_entries(entries),
                },
                backend=self.backend_name,
                db_path=self.db_path,
                dimension=dimension,
                index_type="IndexFlatIP",
                metric_type="COSINE",
                section_metadata="stored",
            )
        except EmbeddingModelUnavailable as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_MISSING,
                str(exc),
                db_path=self.db_path,
                embedding_model=exc.embedding_model,
                fallback_reason=exc.reason,
            )
        except (VectorStoreDimensionMismatch, VectorStoreModelMismatch) as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_CONFLICT,
                str(exc),
                db_path=self.db_path,
                embedding_model=self.embedding_model_name,
            )
        except ValueError as exc:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, str(exc))
        except Exception as exc:
            logger.warning("SQLite+FAISS document upsert failed: %s", exc)
            return ToolResult.fail(
                _vector_store_error_code(exc),
                f"SQLite+FAISS document upsert failed: {exc}",
                db_path=self.db_path,
            )

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: Optional[float] = 0.3,
    ) -> ToolResult:
        """Search normalized vectors with exact inner-product similarity."""
        if not isinstance(query, str) or not query.strip():
            return ToolResult.ok(
                data=[],
                backend=self.backend_name,
                db_path=self.db_path,
                note="Empty query",
            )
        err = check_int_range(top_k, "top_k", TOP_K_MIN, TOP_K_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        if threshold is not None:
            err = check_float_range(
                threshold, "threshold", THRESHOLD_MIN, THRESHOLD_MAX
            )
            if err:
                return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        try:
            self._ensure_encoder()
            query_vector = self._normalize(
                np.asarray(
                    self._encoder.encode([query], normalize_embeddings=True),
                    dtype=np.float32,
                )
            )
            with self._lock:
                self._ensure_index_locked()
                total_docs = len(self._records_by_id)
                if self._index is None or total_docs == 0:
                    return ToolResult.ok(
                        data=[],
                        backend=self.backend_name,
                        db_path=self.db_path,
                        total_docs=0,
                        note="SQLite vector store is empty",
                    )
                if query_vector.shape[1] != self._dimension:
                    raise VectorStoreDimensionMismatch(
                        db_path=self.db_path,
                        existing_dimension=int(self._dimension or 0),
                        expected_dimension=int(query_vector.shape[1]),
                        embedding_model=self.embedding_model_name,
                    )
                candidate_count = min(total_docs, max(top_k * 4, top_k))
                scores, ids = self._index.search(query_vector, candidate_count)
                seen = set()
                results = []
                for score, chunk_id in zip(scores[0], ids[0]):
                    if int(chunk_id) < 0:
                        continue
                    if threshold is not None and float(score) < threshold:
                        continue
                    record = self._records_by_id.get(int(chunk_id))
                    if not record or record["content"] in seen:
                        continue
                    seen.add(record["content"])
                    item = {
                        "content": record["content"],
                        "score": float(score),
                        "index": int(chunk_id),
                        "source": record["source"],
                        "section_path": record["section_path"],
                        "chunk_index": record["chunk_index"],
                    }
                    pid = record.get("parent_section_id", 0)
                    if pid:
                        item["parent_section_id"] = pid
                    results.append(item)
                    if len(results) >= top_k:
                        break
            if self._parent_texts:
                results = _resolve_parent_results(results, self._parent_texts)
            return ToolResult.ok(
                data=results,
                backend=self.backend_name,
                db_path=self.db_path,
                total_docs=total_docs,
                metric_type="COSINE",
                index_type="IndexFlatIP",
                embedding_model=self.embedding_model_name,
            )
        except EmbeddingModelUnavailable as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_MISSING,
                str(exc),
                db_path=self.db_path,
                embedding_model=exc.embedding_model,
                fallback_reason=exc.reason,
            )
        except (VectorStoreDimensionMismatch, VectorStoreModelMismatch) as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_CONFLICT,
                str(exc),
                db_path=self.db_path,
                embedding_model=self.embedding_model_name,
            )
        except Exception as exc:
            logger.warning("SQLite+FAISS search failed: %s", exc)
            return ToolResult.fail(
                _vector_store_error_code(exc),
                f"SQLite+FAISS search failed: {exc}",
                db_path=self.db_path,
            )

    def clear(self) -> ToolResult:
        """Delete only vector-store rows in the configured database."""
        try:
            with self._lock:
                connection = self._ensure_connection_locked()
                with connection:
                    connection.execute("DELETE FROM knowledge_chunks")
                    connection.execute("DELETE FROM vector_store_meta")
                self._index = None
                self._index_ready = True
                self._dimension = None
                self._records_by_id = {}
                self._parent_texts = {}
            return ToolResult.ok(
                data={"cleared": True},
                backend=self.backend_name,
                db_path=self.db_path,
            )
        except Exception as exc:
            return ToolResult.fail(
                _vector_store_error_code(exc),
                f"SQLite+FAISS clear failed: {exc}",
                db_path=self.db_path,
            )

    def delete_sources(self, sources: Sequence[str]) -> ToolResult:
        """Delete all chunks owned by the supplied exact source identifiers.

        The method is intentionally source-scoped: callers cannot provide SQL
        fragments or paths, and an empty input is a successful no-op.
        """
        normalized = list(
            dict.fromkeys(
                str(source).strip()
                for source in sources
                if str(source).strip()
            )
        )
        if not normalized:
            return ToolResult.ok(
                data={"deleted": 0},
                backend=self.backend_name,
                db_path=self.db_path,
            )
        try:
            with self._lock:
                connection = self._ensure_connection_locked()
                placeholders = ",".join("?" for _ in normalized)
                with connection:
                    cursor = connection.execute(
                        f"DELETE FROM knowledge_chunks WHERE source IN ({placeholders})",
                        tuple(normalized),
                    )
                deleted = max(0, int(cursor.rowcount))
                self._index_ready = False
                self._rebuild_index_locked()
            return ToolResult.ok(
                data={"deleted": deleted, "sources": normalized},
                backend=self.backend_name,
                db_path=self.db_path,
            )
        except Exception as exc:
            return ToolResult.fail(
                _vector_store_error_code(exc),
                f"SQLite+FAISS source deletion failed: {exc}",
                db_path=self.db_path,
            )

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._index = None
            self._index_ready = False
            self._records_by_id = {}


class ResilientRetriever:
    """Prefer the configured vector store and hydrate an in-memory fallback on failure."""

    def __init__(
        self,
        primary: Any,
        fallback: MemoryRetriever,
        fallback_enabled: bool = True,
    ):
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled
        self._primary_backend = getattr(primary, "backend_name", "sqlite_faiss")
        self._active_backend = self._primary_backend
        self._documents: List[str] = []
        self._sources: List[str] = []
        self._latest_by_source: Dict[str, str] = {}
        self._fallback_hydrated = False
        self._fallback_reason = ""

    def _activate_fallback(self, failed: ToolResult) -> ToolResult:
        if not self.fallback_enabled:
            return failed
        self._active_backend = "memory"
        self._fallback_reason = failed.error_message or failed.error_code or "unknown"
        if not self._fallback_hydrated:
            documents = list(self._latest_by_source.values()) or self._documents
            sources = list(self._latest_by_source.keys()) or self._sources
            hydrated = self.fallback.add_documents(
                documents,
                sources,
            )
            if not hydrated.ok:
                return hydrated
            self._fallback_hydrated = True
        return ToolResult.ok(
            data={"fallback_activated": True},
            backend="memory",
            degraded=True,
            fallback_from=self._primary_backend,
            fallback_reason=self._fallback_reason,
        )

    def _decorate(self, result: ToolResult) -> ToolResult:
        result.meta.update(
            {
                "backend": "memory",
                "degraded": True,
                "fallback_from": self._primary_backend,
                "fallback_reason": self._fallback_reason,
            }
        )
        return result

    @property
    def document_count(self) -> int:
        if self._active_backend == "memory":
            return self.fallback.document_count
        return self.primary.document_count

    def add_documents(
        self,
        docs: List[str],
        sources: Optional[Sequence[str]] = None,
    ) -> ToolResult:
        normalized_sources = list(sources or [])
        self._documents = list(docs)
        self._sources = [
            normalized_sources[index] if index < len(normalized_sources) else ""
            for index in range(len(docs))
        ]
        for index, doc in enumerate(docs):
            source = self._sources[index]
            if source:
                self._latest_by_source[source] = doc
        if self._active_backend == "memory":
            result = self.fallback.add_documents(docs, normalized_sources)
            return self._decorate(result)
        result = self.primary.add_documents(docs, normalized_sources)
        if result.ok:
            return result
        activated = self._activate_fallback(result)
        if activated.ok:
            return activated
        return result

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: Optional[float] = 0.3,
    ) -> ToolResult:
        if self._active_backend == "memory":
            return self._decorate(self.fallback.search(query, top_k, threshold))
        result = self.primary.search(query, top_k, threshold)
        if result.ok or not self.fallback_enabled:
            return result
        activated = self._activate_fallback(result)
        if not activated.ok:
            return result
        return self._decorate(self.fallback.search(query, top_k, threshold))

    def clear(self) -> ToolResult:
        primary_result = self.primary.clear()
        fallback_result = self.fallback.clear()
        self._documents = []
        self._sources = []
        self._latest_by_source = {}
        self._fallback_hydrated = False
        self._active_backend = self._primary_backend
        self._fallback_reason = ""
        if primary_result.ok and fallback_result.ok:
            return ToolResult.ok(
                data={"cleared": True},
                backend=f"{self._primary_backend}+memory",
            )
        return primary_result if not primary_result.ok else fallback_result

    def close(self) -> None:
        self.primary.close()


# --- Shared Retriever Singleton ---
# Chat and Diet share one configurable retriever so documents are indexed once.

_shared_retriever: Optional[Any] = None
_loaded_knowledge_dirs = set()


def get_shared_retriever():
    """Build the configured dense backend and optionally wrap it with BM25+RRF."""
    global _shared_retriever
    if _shared_retriever is None:
        from app.config import config

        if config.retriever_backend == "sqlite_faiss":
            primary = SQLiteFaissRetriever(
                db_path=config.retriever_db_path,
                embedding_model=config.embedding_model,
                timeout_seconds=config.retriever_timeout_seconds,
            )
            if config.retriever_fallback_to_memory:
                dense_retriever = ResilientRetriever(
                    primary=primary,
                    fallback=MemoryRetriever(
                        embedding_model=config.embedding_model,
                    ),
                    fallback_enabled=True,
                )
            else:
                dense_retriever = primary
        elif config.retriever_backend == "memory":
            dense_retriever = MemoryRetriever(
                embedding_model=config.embedding_model,
            )
        else:
            logger.warning(
                "Unknown RETRIEVER_BACKEND '%s'; using memory backend",
                config.retriever_backend,
            )
            dense_retriever = MemoryRetriever(
                embedding_model=config.embedding_model,
            )
        if config.retriever_strategy == "hybrid":
            _shared_retriever = HybridRetriever(
                dense_retriever,
                candidate_k=config.retriever_candidate_k,
                rrf_k=config.retriever_rrf_k,
            )
        else:
            _shared_retriever = dense_retriever
    return _shared_retriever


def reset_shared_retriever() -> None:
    """Close and clear the shared retriever; intended for tests and reconfiguration."""
    global _shared_retriever
    if _shared_retriever is not None and hasattr(_shared_retriever, "close"):
        _shared_retriever.close()
    _shared_retriever = None
    _loaded_knowledge_dirs.clear()


def load_shared_knowledge_base(docs_dir: str = "data/knowledge") -> None:
    """Load all text files from docs_dir into the shared retriever once.

    Called once at startup from build_router_graph(). Subsequent calls
    are safe no-ops — the retriever skips already-indexed content.
    """
    import os

    normalized_dir = os.path.abspath(docs_dir)
    if normalized_dir in _loaded_knowledge_dirs:
        return
    retriever = get_shared_retriever()
    if not os.path.isdir(docs_dir):
        logger.warning(f"Knowledge directory not found: {docs_dir}")
        return
    loaded = 0
    for fname in sorted(os.listdir(docs_dir)):
        if fname.endswith((".txt", ".md")):
            fpath = os.path.join(docs_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            result = retriever.add_documents([text], sources=[fname])
            if result.ok:
                loaded += 1
                logger.info(
                    "Loaded knowledge: %s (%s chars, backend=%s)",
                    fname,
                    len(text),
                    result.meta.get("backend", "unknown"),
                )
            else:
                logger.error(
                    "Failed to index knowledge %s: %s",
                    fname,
                    result.error_message,
                )
    if loaded:
        _loaded_knowledge_dirs.add(normalized_dir)
        logger.info(f"Shared knowledge base: {retriever.document_count} chunks "
                     f"from {loaded} files")

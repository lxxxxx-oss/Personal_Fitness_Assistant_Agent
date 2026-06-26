"""向量检索模块 — Demo阶段使用内存存储,后期替换为Milvus.

PERMISSION: This tool retrieves pre-loaded knowledge content only.
It does NOT perform fact-checking, verify medical claims, or access
external data sources. Retrieved content may be outdated or incomplete.
Users should consult professionals for medical or training decisions.
"""

import logging
import re
from typing import Dict, List, Optional

import numpy as np

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


class MemoryRetriever:
    """基于内存的向量检索器.

    使用 Sentence-Transformer 编码文本,NumPy 存储向量,
    余弦相似度检索 + 阈值过滤 + 去重排序后处理.

    Input:
        search(query: str, top_k: int=5, threshold: float=0.3)

    Output:
        ToolResult.data = [{"content": str, "score": float, "index": int}, ...]
        ToolResult.meta = {"mode": "embedding" | "keyword", "total_docs": int}
    """

    def __init__(
        self,
        embedding_model: str = "shibing624/text2vec-base-chinese",
        device: str = "cpu",
    ):
        self.embedding_model_name = embedding_model
        self.device = device
        self._encoder = None
        self._documents: List[str] = []
        self._embeddings: Optional[np.ndarray] = None

    def _ensure_encoder(self):
        """延迟加载 Sentence-Transformer 编码器."""
        if self._encoder is not None:
            return

        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        try:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(
                self.embedding_model_name, device=self.device
            )
        except Exception as e:
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
                    results.append({
                        "content": self._documents[idx],
                        "score": score,
                        "index": idx,
                    })

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
                    existing = [r for r in results if r["index"] == idx]
                    if not existing:
                        results.append({
                            "content": self._documents[idx],
                            "score": substring_score,
                            "index": idx,
                        })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def add_documents(self, docs: List[str]) -> None:
        """添加文档到检索库(自动分块后编码)."""
        self._ensure_encoder()
        chunks = []
        for doc in docs:
            chunks.extend(_chinese_sentence_split(doc))
        if not chunks:
            return
        self._documents.extend(chunks)
        if self._encoder is not None:
            new_embeddings = self._encoder.encode(chunks, normalize_embeddings=True)
            if self._embeddings is None:
                self._embeddings = new_embeddings
            else:
                self._embeddings = np.vstack([self._embeddings, new_embeddings])
        logger.info(f"Added {len(chunks)} chunks, total: {len(self._documents)}")

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
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
        err = check_float_range(threshold, "threshold", THRESHOLD_MIN, THRESHOLD_MAX)
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

        # 阈值过滤 → 索引排序 → 取top_k
        qualified = np.where(scores >= threshold)[0]
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
            results.append({
                "content": content,
                "score": float(scores[int(idx)]),
                "index": int(idx),
            })
        return ToolResult.ok(
            data=results,
            mode="embedding",
            total_docs=len(self._documents),
        )

    def clear(self) -> None:
        """清空全部文档和向量."""
        self._documents = []
        self._embeddings = None


def _chinese_sentence_split(text: str, max_chunk_chars: int = 500) -> List[str]:
    """Sentence-aware text chunking (supports both Chinese and English).

    Splits on natural sentence boundaries — Chinese/English punctuation
    and newlines. Long sentences are further split by max_chunk_chars.
    """
    sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
    chunks = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) <= max_chunk_chars:
            current += sent
        else:
            if current:
                chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    return chunks or [text]


# --- Shared Retriever Singleton ---
# Chat and Diet subgraphs share a single MemoryRetriever instance
# to avoid loading the same knowledge base twice.

_shared_retriever: Optional[MemoryRetriever] = None


def get_shared_retriever() -> MemoryRetriever:
    """Get or create the global shared MemoryRetriever singleton.

    Both Chat and Diet subgraphs use this same instance, so the
    knowledge base is only embedded once.
    """
    global _shared_retriever
    if _shared_retriever is None:
        from app.config import config

        _shared_retriever = MemoryRetriever(
            embedding_model=config.embedding_model,
        )
    return _shared_retriever


def load_shared_knowledge_base(docs_dir: str = "data/knowledge") -> None:
    """Load all text files from docs_dir into the shared retriever once.

    Called once at startup from build_router_graph(). Subsequent calls
    are safe no-ops — the retriever skips already-indexed content.
    """
    import os

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
            retriever.add_documents([text])
            loaded += 1
            logger.info(f"Loaded knowledge: {fname} ({len(text)} chars)")
    if loaded:
        logger.info(f"Shared knowledge base: {retriever.document_count} chunks "
                     f"from {loaded} files")

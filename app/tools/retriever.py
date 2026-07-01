"""向量检索模块 — Demo阶段使用内存存储,后期替换为Milvus.

PERMISSION: This tool retrieves pre-loaded knowledge content only.
It does NOT perform fact-checking, verify medical claims, or access
external data sources. Retrieved content may be outdated or incomplete.
Users should consult professionals for medical or training decisions.
"""

import logging
import re
import hashlib
from typing import Any, Dict, List, Optional, Tuple

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
        self._sources: List[str] = []
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
                        "source": self._sources[idx] if idx < len(self._sources) else "",
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
                            "source": self._sources[idx] if idx < len(self._sources) else "",
                        })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    @property
    def document_count(self) -> int:
        return len(self._documents)

    def add_documents(self, docs: List[str], source: Optional[str] = None) -> None:
        """添加文档到检索库(自动分块后编码)."""
        self._ensure_encoder()
        chunks = []
        for doc in docs:
            chunks.extend(_chinese_sentence_split(doc))
        if not chunks:
            return
        self._documents.extend(chunks)
        self._sources.extend([source or ""] * len(chunks))
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
                "source": self._sources[int(idx)] if int(idx) < len(self._sources) else "",
            })
        return ToolResult.ok(
            data=results,
            mode="embedding",
            total_docs=len(self._documents),
        )

    def clear(self) -> None:
        """清空全部文档和向量."""
        self._documents = []
        self._sources = []
        self._embeddings = None


class MilvusRetriever:
    """Milvus-backed retriever with MemoryRetriever fallback.

    The public contract intentionally matches MemoryRetriever so Chat/Diet
    subgraphs do not need to know which vector store is active.
    """

    def __init__(
        self,
        embedding_model: str = "shibing624/text2vec-base-chinese",
        device: str = "cpu",
        uri: str = "http://localhost:19530",
        token: str = "",
        collection_name: str = "fitness_knowledge",
        recreate_collection: bool = False,
        index_type: str = "IVF_FLAT",
        metric_type: str = "COSINE",
        nlist: int = 128,
        nprobe: int = 10,
    ):
        self.embedding_model_name = embedding_model
        self.device = device
        self.uri = uri
        self.token = token
        self.collection_name = collection_name
        self.recreate_collection = recreate_collection
        self.index_type = index_type
        self.metric_type = metric_type
        self.nlist = nlist
        self.nprobe = nprobe
        self._encoder = None
        self._client = None
        self._collection_ready = False
        self._disabled_reason: Optional[str] = None
        self._document_count = 0
        self._fallback = MemoryRetriever(embedding_model=embedding_model, device=device)

    @property
    def document_count(self) -> int:
        if self._disabled_reason:
            return self._fallback.document_count
        return self._document_count

    def _ensure_encoder(self) -> bool:
        if self._encoder is not None:
            return True
        try:
            from sentence_transformers import SentenceTransformer

            self._encoder = SentenceTransformer(
                self.embedding_model_name, device=self.device
            )
            return True
        except Exception as e:
            self._disabled_reason = (
                f"Cannot load embedding model '{self.embedding_model_name}': {e}"
            )
            logger.warning("%s. Falling back to MemoryRetriever.", self._disabled_reason)
            return False

    def _ensure_client(self) -> bool:
        if self._client is not None:
            return True
        try:
            from pymilvus import MilvusClient

            kwargs = {"uri": self.uri}
            if self.token:
                kwargs["token"] = self.token
            self._client = MilvusClient(**kwargs)
            return True
        except Exception as e:
            self._disabled_reason = f"Cannot connect to Milvus at {self.uri}: {e}"
            logger.warning("%s. Falling back to MemoryRetriever.", self._disabled_reason)
            return False

    def _has_collection(self) -> bool:
        try:
            return bool(self._client.has_collection(self.collection_name))
        except Exception:
            return False

    def _ensure_collection(self, dim: Optional[int] = None) -> bool:
        if not self._ensure_client():
            return False
        try:
            from pymilvus import DataType

            if self.recreate_collection and self._has_collection():
                self._client.drop_collection(self.collection_name)
                self._collection_ready = False
                self._document_count = 0

            if self._has_collection():
                self._collection_ready = True
                return True

            if dim is None:
                self._disabled_reason = "Milvus collection is missing and dim is unknown"
                return False

            schema = self._client.create_schema(
                auto_id=False,
                enable_dynamic_field=False,
            )
            schema.add_field(
                field_name="id",
                datatype=DataType.VARCHAR,
                is_primary=True,
                max_length=64,
            )
            schema.add_field(
                field_name="content",
                datatype=DataType.VARCHAR,
                max_length=8192,
            )
            schema.add_field(
                field_name="source",
                datatype=DataType.VARCHAR,
                max_length=512,
            )
            schema.add_field(
                field_name="embedding",
                datatype=DataType.FLOAT_VECTOR,
                dim=dim,
            )

            index_params = self._client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                index_type=self.index_type,
                metric_type=self.metric_type,
                params={"nlist": self.nlist},
            )
            self._client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index_params,
            )
            self._collection_ready = True
            logger.info("Created Milvus collection: %s", self.collection_name)
            return True
        except Exception as e:
            self._disabled_reason = f"Cannot initialize Milvus collection: {e}"
            logger.warning("%s. Falling back to MemoryRetriever.", self._disabled_reason)
            return False

    def _split_docs(
        self, docs: List[str], source: Optional[str] = None
    ) -> List[Tuple[str, str]]:
        chunks: List[Tuple[str, str]] = []
        for doc in docs:
            for chunk in _chinese_sentence_split(doc):
                chunks.append((chunk, source or ""))
        return chunks

    def _chunk_id(self, content: str, source: str) -> str:
        raw = f"{source}\n{content}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def add_documents(self, docs: List[str], source: Optional[str] = None) -> None:
        chunks = self._split_docs(docs, source=source)
        if not chunks:
            return

        if not self._ensure_encoder():
            self._fallback.add_documents(docs, source=source)
            return

        try:
            texts = [content for content, _ in chunks]
            embeddings = self._encoder.encode(texts, normalize_embeddings=True)
            dim = int(embeddings.shape[1])
            if not self._ensure_collection(dim=dim):
                self._fallback.add_documents(docs, source=source)
                return

            rows = []
            for (content, chunk_source), embedding in zip(chunks, embeddings):
                rows.append(
                    {
                        "id": self._chunk_id(content, chunk_source),
                        "content": content[:8192],
                        "source": chunk_source[:512],
                        "embedding": embedding.astype(float).tolist(),
                    }
                )

            if hasattr(self._client, "upsert"):
                self._client.upsert(collection_name=self.collection_name, data=rows)
            else:
                self._client.insert(collection_name=self.collection_name, data=rows)
            if hasattr(self._client, "flush"):
                self._client.flush(collection_name=self.collection_name)
            if hasattr(self._client, "load_collection"):
                self._client.load_collection(collection_name=self.collection_name)
            self._document_count += len(rows)
            logger.info(
                "Added %s chunks to Milvus collection %s",
                len(rows),
                self.collection_name,
            )
        except Exception as e:
            self._disabled_reason = f"Milvus insert failed: {e}"
            logger.warning("%s. Falling back to MemoryRetriever.", self._disabled_reason)
            self._fallback.add_documents(docs, source=source)

    def _parse_hit(self, hit: Any) -> Dict[str, Any]:
        if isinstance(hit, dict):
            entity = hit.get("entity") or hit.get("fields") or {}
            return {
                "id": hit.get("id") or hit.get("pk") or entity.get("id"),
                "score": hit.get("distance", hit.get("score", 0.0)),
                "content": entity.get("content", hit.get("content", "")),
                "source": entity.get("source", hit.get("source", "")),
            }
        entity = getattr(hit, "entity", {}) or {}
        getter = entity.get if hasattr(entity, "get") else lambda key, default=None: default
        return {
            "id": getattr(hit, "id", None),
            "score": getattr(hit, "distance", getattr(hit, "score", 0.0)),
            "content": getter("content", ""),
            "source": getter("source", ""),
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> ToolResult:
        if self._disabled_reason:
            result = self._fallback.search(query, top_k=top_k, threshold=threshold)
            result.meta["backend"] = "milvus_fallback"
            result.meta["fallback_reason"] = self._disabled_reason
            return result
        if not isinstance(query, str) or not query.strip():
            return ToolResult.ok(
                data=[],
                mode="milvus",
                total_docs=self.document_count,
                note="Empty query",
            )
        err = check_int_range(top_k, "top_k", TOP_K_MIN, TOP_K_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        err = check_float_range(threshold, "threshold", THRESHOLD_MIN, THRESHOLD_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        if not self._ensure_encoder() or not self._ensure_collection():
            result = self._fallback.search(query, top_k=top_k, threshold=threshold)
            result.meta["backend"] = "milvus_fallback"
            result.meta["fallback_reason"] = self._disabled_reason
            return result

        try:
            query_vec = self._encoder.encode([query], normalize_embeddings=True)[0]
            search_kwargs = {
                "collection_name": self.collection_name,
                "data": [query_vec.astype(float).tolist()],
                "search_params": {
                    "metric_type": self.metric_type,
                    "params": {"nprobe": self.nprobe},
                },
                "limit": top_k,
                "output_fields": ["content", "source"],
            }
            try:
                raw = self._client.search(anns_field="embedding", **search_kwargs)
            except TypeError:
                raw = self._client.search(**search_kwargs)
            hits = raw[0] if raw else []
            results = []
            seen = set()
            for rank, hit in enumerate(hits):
                parsed = self._parse_hit(hit)
                score = float(parsed["score"] or 0.0)
                content = parsed["content"] or ""
                if score < threshold or not content:
                    continue
                normalized = content.strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                results.append(
                    {
                        "content": content,
                        "score": score,
                        "index": parsed["id"] or rank,
                        "source": parsed["source"] or "",
                    }
                )
            return ToolResult.ok(
                data=results,
                mode="milvus",
                total_docs=self.document_count,
                collection=self.collection_name,
            )
        except Exception as e:
            self._disabled_reason = f"Milvus search failed: {e}"
            logger.warning("%s. Falling back to MemoryRetriever.", self._disabled_reason)
            result = self._fallback.search(query, top_k=top_k, threshold=threshold)
            result.meta["backend"] = "milvus_fallback"
            result.meta["fallback_reason"] = self._disabled_reason
            return result

    def clear(self) -> None:
        if self._client is not None and self._has_collection():
            self._client.drop_collection(self.collection_name)
        self._collection_ready = False
        self._document_count = 0
        self._fallback.clear()


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
# Chat and Diet subgraphs share a single retriever instance
# to avoid loading the same knowledge base twice.

_shared_retriever: Optional[Any] = None
_loaded_knowledge_dirs: set[str] = set()


def get_shared_retriever() -> Any:
    """Get or create the global shared retriever singleton.

    Both Chat and Diet subgraphs use this same instance, so the
    knowledge base is only embedded once.
    """
    global _shared_retriever
    if _shared_retriever is None:
        from app.config import config

        if config.retriever_backend == "milvus":
            _shared_retriever = MilvusRetriever(
                embedding_model=config.embedding_model,
                uri=config.milvus_uri,
                token=config.milvus_token,
                collection_name=config.milvus_collection,
                recreate_collection=config.milvus_recreate_collection,
                index_type=config.milvus_index_type,
                metric_type=config.milvus_metric_type,
                nlist=config.milvus_nlist,
                nprobe=config.milvus_nprobe,
            )
            logger.info("Using Milvus retriever backend: %s", config.milvus_uri)
        else:
            _shared_retriever = MemoryRetriever(
                embedding_model=config.embedding_model,
            )
            logger.info("Using memory retriever backend")
    return _shared_retriever


def load_shared_knowledge_base(docs_dir: str = "data/knowledge") -> None:
    """Load all text files from docs_dir into the shared retriever once.

    Called once at startup from build_router_graph(). Subsequent calls
    are safe no-ops — the retriever skips already-indexed content.
    """
    import os

    retriever = get_shared_retriever()
    normalized_dir = os.path.abspath(docs_dir)
    if normalized_dir in _loaded_knowledge_dirs:
        logger.info("Knowledge directory already loaded: %s", docs_dir)
        return
    if not os.path.isdir(docs_dir):
        logger.warning(f"Knowledge directory not found: {docs_dir}")
        return
    loaded = 0
    for fname in sorted(os.listdir(docs_dir)):
        if fname.endswith((".txt", ".md")):
            fpath = os.path.join(docs_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            retriever.add_documents([text], source=fname)
            loaded += 1
            logger.info(f"Loaded knowledge: {fname} ({len(text)} chars)")
    if loaded:
        _loaded_knowledge_dirs.add(normalized_dir)
        logger.info(f"Shared knowledge base: {retriever.document_count} chunks "
                     f"from {loaded} files")

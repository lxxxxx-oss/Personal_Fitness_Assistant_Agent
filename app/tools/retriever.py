"""向量检索模块 — Demo阶段使用内存存储,后期替换为Milvus.

PERMISSION: This tool retrieves pre-loaded knowledge content only.
It does NOT perform fact-checking, verify medical claims, or access
external data sources. Retrieved content may be outdated or incomplete.
Users should consult professionals for medical or training decisions.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.config import DEFAULT_EMBEDDING_MODEL, DEFAULT_KNOWLEDGE_COLLECTION, config
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
        self._chunk_ids: List[int] = []
        self._source_latest_ids: Dict[str, List[int]] = {}
        self._embeddings: Optional[np.ndarray] = None

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
                    results.append({
                        "content": self._documents[idx],
                        "score": score,
                        "index": self._chunk_ids[idx],
                        "source": self._sources[idx],
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
                    existing = [
                        r for r in results if r["index"] == self._chunk_ids[idx]
                    ]
                    if not existing:
                        results.append({
                            "content": self._documents[idx],
                            "score": substring_score,
                            "index": self._chunk_ids[idx],
                            "source": self._sources[idx],
                        })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

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
        self._chunk_ids = [self._chunk_ids[index] for index in keep_indices]
        if self._embeddings is not None:
            self._embeddings = self._embeddings[keep_indices]
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
        chunk_sources = [entry["source"] for entry in entries]
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
        self._documents.extend(chunks)
        self._sources.extend(chunk_sources)
        self._chunk_ids.extend(incoming_ids)
        if self._encoder is not None:
            new_embeddings = self._encoder.encode(chunks, normalize_embeddings=True)
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
                "index": int(self._chunk_ids[int(idx)]),
                "source": self._sources[int(idx)],
            })
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
        self._chunk_ids = []
        self._source_latest_ids = {}
        self._embeddings = None
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


def _chinese_sentence_split(
    text: str,
    max_chunk_chars: int = 500,
    overlap_chars: int = 0,
) -> List[str]:
    """Sentence-aware text chunking (supports both Chinese and English).

    Splits on natural sentence boundaries — Chinese/English punctuation
    and newlines. Long sentences are further split by max_chunk_chars.
    """
    max_chunk_chars = max(1, int(max_chunk_chars))
    overlap_chars = max(0, int(overlap_chars))
    sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
    chunks = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) > max_chunk_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_segment(sent, max_chunk_chars, overlap_chars))
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


def _content_hash(content: str) -> str:
    """Build a stable content hash for manifest and chunk identity."""
    return hashlib.blake2b(content.encode("utf-8"), digest_size=16).hexdigest()


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
    """Chunk documents and attach versioned identity metadata."""
    normalized_sources = list(sources or [])
    entries: List[Dict[str, Any]] = []
    version = str(config.retriever_knowledge_version or "v1")
    for doc_index, doc in enumerate(docs):
        source = (
            str(normalized_sources[doc_index])[:1024]
            if doc_index < len(normalized_sources)
            else ""
        )
        chunks = [
            chunk
            for chunk in _chinese_sentence_split(
                doc,
                max_chunk_chars=config.retriever_chunk_chars,
                overlap_chars=config.retriever_chunk_overlap_chars,
            )
            if chunk.strip()
        ]
        for chunk_index, content in enumerate(chunks):
            entries.append(
                {
                    "id": _stable_chunk_id(
                        content,
                        source=source,
                        chunk_index=chunk_index,
                        version=version,
                    ),
                    "content": content,
                    "source": source,
                    "chunk_index": chunk_index,
                    "content_hash": _content_hash(content),
                    "version": version,
                }
            )
    return entries


def _manifest_from_entries(entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a compact ingestion manifest safe to expose in ToolResult."""
    sources: Dict[str, Dict[str, Any]] = {}
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
            },
        )
        bucket["chunk_count"] += 1
        bucket["chunk_ids"].append(int(entry["id"]))
        bucket["content_hashes"].append(str(entry["content_hash"]))
    return {
        "version": str(config.retriever_knowledge_version or "v1"),
        "source_count": len(sources),
        "chunk_count": len(entries),
        "sources": list(sources.values()),
    }


def _milvus_error_code(exc: Exception) -> str:
    """Classify Milvus SDK failures into the shared tool error taxonomy."""
    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return ErrorCode.CONFIG_MISSING
    message = str(exc).lower()
    network_markers = (
        "connection",
        "refused",
        "unavailable",
        "timeout",
        "timed out",
        "grpc",
        "failed to connect",
    )
    if any(marker in message for marker in network_markers):
        return ErrorCode.NETWORK_ERROR
    return ErrorCode.INTERNAL_ERROR


class CollectionDimensionMismatch(ValueError):
    """Raised when an embedding model cannot reuse an existing collection."""

    def __init__(
        self,
        *,
        collection: str,
        existing_dimension: int,
        expected_dimension: int,
        embedding_model: str,
    ) -> None:
        self.collection = collection
        self.existing_dimension = existing_dimension
        self.expected_dimension = expected_dimension
        self.embedding_model = embedding_model
        self.recommended_collection = f"{collection}_dim{expected_dimension}"
        super().__init__(
            f"Milvus collection '{collection}' has vector dimension "
            f"{existing_dimension}, but embedding model '{embedding_model}' returns "
            f"{expected_dimension}. Keep the old collection for rollback and set "
            f"MILVUS_COLLECTION_NAME={self.recommended_collection}, then re-index "
            "the knowledge files."
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


class MilvusRetriever:
    """Persistent vector retriever backed by a configured Milvus collection.

    Responsibility:
        Store sentence-aware chunks and normalized embeddings in exactly one
        configured collection, then return thresholded COSINE matches.

    Permission boundary:
        The retriever can create, upsert, search, load, flush, and drop only
        ``collection_name`` on ``uri``. It never executes user-provided SQL,
        shell commands, or arbitrary collection operations.

    Public contract:
        ``add_documents`` and ``search`` return ``ToolResult``. Search results
        keep the existing shape: content, score, index, and source.
    """

    _COLLECTION_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,254}$")
    _SUPPORTED_INDEX_TYPES = {"IVF_FLAT", "FLAT"}
    _SUPPORTED_METRICS = {"COSINE"}

    def __init__(
        self,
        uri: str,
        collection_name: str = DEFAULT_KNOWLEDGE_COLLECTION,
        token: str = "",
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        device: str = "cpu",
        index_type: str = "IVF_FLAT",
        metric_type: str = "COSINE",
        nlist: int = 128,
        nprobe: int = 16,
        timeout_seconds: float = 3.0,
    ):
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError("uri must be a non-empty string")
        if not self._COLLECTION_NAME_RE.fullmatch(collection_name):
            raise ValueError(
                "collection_name must start with a letter or underscore and "
                "contain only letters, digits, or underscores"
            )
        normalized_index = index_type.upper()
        normalized_metric = metric_type.upper()
        if normalized_index not in self._SUPPORTED_INDEX_TYPES:
            raise ValueError(
                f"Unsupported Milvus index_type: {normalized_index}"
            )
        if normalized_metric not in self._SUPPORTED_METRICS:
            raise ValueError(
                f"Unsupported Milvus metric_type: {normalized_metric}"
            )
        if nlist < 1 or nprobe < 1:
            raise ValueError("nlist and nprobe must be positive integers")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self.uri = uri.strip()
        self.collection_name = collection_name
        self.token = token
        self.embedding_model_name = embedding_model
        self.device = device
        self.index_type = normalized_index
        self.metric_type = normalized_metric
        self.nlist = nlist
        self.nprobe = nprobe
        self.timeout_seconds = timeout_seconds
        self._encoder = None
        self._client = None
        self._milvus_client_type = None
        self._data_type = None
        self._dimension: Optional[int] = None
        self._source_latest_ids: Dict[str, List[int]] = {}

    def _ensure_encoder(self):
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

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        from pymilvus import DataType, MilvusClient

        kwargs: Dict[str, Any] = {
            "uri": self.uri,
            "timeout": self.timeout_seconds,
        }
        if self.token:
            kwargs["token"] = self.token
        self._client = MilvusClient(**kwargs)
        self._milvus_client_type = MilvusClient
        self._data_type = DataType
        return self._client

    @staticmethod
    def _vector_dimension(description: Dict[str, Any]) -> Optional[int]:
        for field in description.get("fields", []):
            if field.get("name") != "vector":
                continue
            params = field.get("params", {})
            dimension = params.get("dim")
            return int(dimension) if dimension is not None else None
        return None

    def _ensure_collection(self, dimension: int) -> None:
        client = self._ensure_client()
        if client.has_collection(collection_name=self.collection_name):
            description = client.describe_collection(
                collection_name=self.collection_name
            )
            existing_dimension = self._vector_dimension(description)
            if existing_dimension is not None and existing_dimension != dimension:
                raise CollectionDimensionMismatch(
                    collection=self.collection_name,
                    existing_dimension=existing_dimension,
                    expected_dimension=dimension,
                    embedding_model=self.embedding_model_name,
                )
            self._dimension = dimension
            self._ensure_index()
            client.load_collection(collection_name=self.collection_name)
            return

        schema = self._milvus_client_type.create_schema(
            auto_id=False,
            enable_dynamic_field=False,
        )
        schema.add_field(
            field_name="id",
            datatype=self._data_type.INT64,
            is_primary=True,
        )
        schema.add_field(
            field_name="vector",
            datatype=self._data_type.FLOAT_VECTOR,
            dim=dimension,
        )
        schema.add_field(
            field_name="content",
            datatype=self._data_type.VARCHAR,
            max_length=65535,
        )
        schema.add_field(
            field_name="source",
            datatype=self._data_type.VARCHAR,
            max_length=1024,
        )
        client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            consistency_level="Strong",
        )

        self._ensure_index()
        client.load_collection(collection_name=self.collection_name)
        self._dimension = dimension

    def _ensure_index(self) -> None:
        """Create the configured vector index when the collection lacks it."""
        client = self._ensure_client()
        existing = client.list_indexes(collection_name=self.collection_name)
        existing_names = {
            item if isinstance(item, str) else item.get("index_name", "")
            for item in (existing or [])
        }
        if "vector_index" in existing_names:
            return

        index_params = self._milvus_client_type.prepare_index_params()
        index_kwargs: Dict[str, Any] = {
            "field_name": "vector",
            "index_name": "vector_index",
            "index_type": self.index_type,
            "metric_type": self.metric_type,
        }
        if self.index_type == "IVF_FLAT":
            index_kwargs["params"] = {"nlist": self.nlist}
        index_params.add_index(**index_kwargs)
        client.create_index(
            collection_name=self.collection_name,
            index_params=index_params,
        )

    @property
    def document_count(self) -> int:
        try:
            client = self._ensure_client()
            if not client.has_collection(collection_name=self.collection_name):
                return 0
            stats = client.get_collection_stats(
                collection_name=self.collection_name
            )
            return int(stats.get("row_count", 0))
        except Exception:
            return 0

    def _delete_chunk_ids(self, chunk_ids: Sequence[int]) -> int:
        """Delete known stale chunks by primary key from this collection."""
        ids = [int(chunk_id) for chunk_id in chunk_ids]
        if not ids:
            return 0
        client = self._ensure_client()
        result = client.delete(collection_name=self.collection_name, ids=ids)
        if isinstance(result, dict):
            deleted = result.get("delete_count")
            if deleted is not None:
                return int(deleted)
        return 0

    def add_documents(
        self,
        docs: List[str],
        sources: Optional[Sequence[str]] = None,
    ) -> ToolResult:
        """Chunk, encode, and idempotently upsert documents into Milvus."""
        if not isinstance(docs, list) or any(not isinstance(doc, str) for doc in docs):
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                "docs must be a list of strings",
            )
        normalized_sources = list(sources or [])
        entries = _build_chunk_entries(docs, normalized_sources)
        if not entries:
            return ToolResult.ok(
                data={"upserted": 0},
                backend="milvus",
                collection=self.collection_name,
            )
        chunks = [str(entry["content"]) for entry in entries]

        try:
            self._ensure_encoder()
            embeddings = np.asarray(
                self._encoder.encode(chunks, normalize_embeddings=True),
                dtype=np.float32,
            )
            if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
                raise ValueError(
                    "Embedding model returned an invalid matrix shape: "
                    f"{embeddings.shape}"
                )
            self._ensure_collection(int(embeddings.shape[1]))
            incoming_ids = [int(entry["id"]) for entry in entries]
            removed = self._delete_chunk_ids(incoming_ids)
            source_groups: Dict[str, List[int]] = {}
            for entry in entries:
                source = str(entry["source"])
                if source:
                    source_groups.setdefault(source, []).append(int(entry["id"]))
            stale_removed = 0
            for source, new_ids in source_groups.items():
                new_id_set = set(new_ids)
                stale_ids = [
                    chunk_id
                    for chunk_id in self._source_latest_ids.get(source, [])
                    if chunk_id not in new_id_set
                ]
                stale_removed += self._delete_chunk_ids(stale_ids)
                self._source_latest_ids[source] = list(new_ids)
            rows = [
                {
                    "id": int(entry["id"]),
                    "vector": embeddings[index].tolist(),
                    "content": str(entry["content"]),
                    "source": str(entry["source"]),
                }
                for index, entry in enumerate(entries)
            ]
            result = self._client.upsert(
                collection_name=self.collection_name,
                data=rows,
            )
            self._client.flush(collection_name=self.collection_name)
            return ToolResult.ok(
                data={
                    "upserted": len(rows),
                    "removed": removed + stale_removed,
                    "primary_keys": result.get("primary_keys", []),
                    "manifest": _manifest_from_entries(entries),
                },
                backend="milvus",
                collection=self.collection_name,
                dimension=int(embeddings.shape[1]),
            )
        except EmbeddingModelUnavailable as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_MISSING,
                str(exc),
                collection=self.collection_name,
                embedding_model=exc.embedding_model,
                fallback_reason=exc.reason,
            )
        except CollectionDimensionMismatch as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_CONFLICT,
                str(exc),
                collection=exc.collection,
                embedding_model=exc.embedding_model,
                existing_dimension=exc.existing_dimension,
                expected_dimension=exc.expected_dimension,
                recommended_collection=exc.recommended_collection,
            )
        except ValueError as exc:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, str(exc))
        except Exception as exc:
            logger.warning("Milvus document upsert failed: %s", exc)
            return ToolResult.fail(
                _milvus_error_code(exc),
                f"Milvus document upsert failed: {exc}",
                collection=self.collection_name,
            )

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> ToolResult:
        """Search the configured Milvus collection using vector similarity."""
        if not isinstance(query, str) or not query.strip():
            return ToolResult.ok(
                data=[],
                backend="milvus",
                collection=self.collection_name,
                note="Empty query",
            )
        err = check_int_range(top_k, "top_k", TOP_K_MIN, TOP_K_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)
        err = check_float_range(threshold, "threshold", THRESHOLD_MIN, THRESHOLD_MAX)
        if err:
            return ToolResult.fail(ErrorCode.INVALID_PARAM, err)

        try:
            self._ensure_encoder()
            client = self._ensure_client()
            if not client.has_collection(collection_name=self.collection_name):
                return ToolResult.ok(
                    data=[],
                    backend="milvus",
                    collection=self.collection_name,
                    total_docs=0,
                    note="Milvus collection is empty",
                )
            query_vector = np.asarray(
                self._encoder.encode([query], normalize_embeddings=True),
                dtype=np.float32,
            )
            self._ensure_collection(int(query_vector.shape[1]))
            raw = client.search(
                collection_name=self.collection_name,
                data=[query_vector[0].tolist()],
                anns_field="vector",
                search_params={
                    "metric_type": self.metric_type,
                    "params": {"nprobe": self.nprobe},
                },
                limit=top_k,
                output_fields=["content", "source"],
                consistency_level="Strong",
            )
            hits = raw[0] if raw else []
            seen = set()
            results = []
            for hit in hits:
                score = float(hit.get("distance", hit.get("score", 0.0)))
                if score < threshold:
                    continue
                entity = hit.get("entity", {}) or {}
                content = entity.get("content", "")
                if not content or content in seen:
                    continue
                seen.add(content)
                results.append(
                    {
                        "content": content,
                        "score": score,
                        "index": int(hit.get("id", _stable_chunk_id(content))),
                        "source": entity.get("source", ""),
                    }
                )
            return ToolResult.ok(
                data=results,
                backend="milvus",
                collection=self.collection_name,
                total_docs=self.document_count,
                metric_type=self.metric_type,
                index_type=self.index_type,
                embedding_model=self.embedding_model_name,
            )
        except EmbeddingModelUnavailable as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_MISSING,
                str(exc),
                collection=self.collection_name,
                embedding_model=exc.embedding_model,
                fallback_reason=exc.reason,
            )
        except CollectionDimensionMismatch as exc:
            return ToolResult.fail(
                ErrorCode.CONFIG_CONFLICT,
                str(exc),
                collection=exc.collection,
                embedding_model=exc.embedding_model,
                existing_dimension=exc.existing_dimension,
                expected_dimension=exc.expected_dimension,
                recommended_collection=exc.recommended_collection,
            )
        except Exception as exc:
            logger.warning("Milvus search failed: %s", exc)
            return ToolResult.fail(
                _milvus_error_code(exc),
                f"Milvus search failed: {exc}",
                collection=self.collection_name,
            )

    def clear(self) -> ToolResult:
        """Drop only the configured collection and reset local state."""
        try:
            client = self._ensure_client()
            if client.has_collection(collection_name=self.collection_name):
                client.drop_collection(collection_name=self.collection_name)
            self._dimension = None
            self._source_latest_ids = {}
            return ToolResult.ok(
                data={"cleared": True},
                backend="milvus",
                collection=self.collection_name,
            )
        except Exception as exc:
            return ToolResult.fail(
                _milvus_error_code(exc),
                f"Milvus clear failed: {exc}",
                collection=self.collection_name,
            )

    def close(self) -> None:
        if self._client is not None and hasattr(self._client, "close"):
            self._client.close()
        self._client = None


class ResilientRetriever:
    """Prefer Milvus and hydrate an in-memory fallback after a Milvus failure."""

    def __init__(
        self,
        primary: MilvusRetriever,
        fallback: MemoryRetriever,
        fallback_enabled: bool = True,
    ):
        self.primary = primary
        self.fallback = fallback
        self.fallback_enabled = fallback_enabled
        self._active_backend = "milvus"
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
            fallback_from="milvus",
            fallback_reason=self._fallback_reason,
        )

    def _decorate(self, result: ToolResult) -> ToolResult:
        result.meta.update(
            {
                "backend": "memory",
                "fallback_from": "milvus",
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
        threshold: float = 0.3,
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
        self._active_backend = "milvus"
        self._fallback_reason = ""
        if primary_result.ok and fallback_result.ok:
            return ToolResult.ok(data={"cleared": True}, backend="milvus+memory")
        return primary_result if not primary_result.ok else fallback_result

    def close(self) -> None:
        self.primary.close()


# --- Shared Retriever Singleton ---
# Chat and Diet share one configurable retriever so documents are indexed once.

_shared_retriever: Optional[Any] = None
_loaded_knowledge_dirs = set()


def get_shared_retriever():
    """Get the shared Milvus-backed retriever or the configured memory backend."""
    global _shared_retriever
    if _shared_retriever is None:
        from app.config import config

        if config.retriever_backend == "milvus":
            primary = MilvusRetriever(
                uri=config.milvus_uri,
                collection_name=config.milvus_collection_name,
                token=config.milvus_token,
                embedding_model=config.embedding_model,
                index_type=config.milvus_index_type,
                nlist=config.milvus_nlist,
                nprobe=config.milvus_nprobe,
                timeout_seconds=config.milvus_timeout_seconds,
            )
            if config.retriever_fallback_to_memory:
                _shared_retriever = ResilientRetriever(
                    primary=primary,
                    fallback=MemoryRetriever(
                        embedding_model=config.embedding_model,
                    ),
                    fallback_enabled=True,
                )
            else:
                _shared_retriever = primary
        elif config.retriever_backend == "memory":
            _shared_retriever = MemoryRetriever(
                embedding_model=config.embedding_model,
            )
        else:
            logger.warning(
                "Unknown RETRIEVER_BACKEND '%s'; using memory backend",
                config.retriever_backend,
            )
            _shared_retriever = MemoryRetriever(
                embedding_model=config.embedding_model,
            )
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

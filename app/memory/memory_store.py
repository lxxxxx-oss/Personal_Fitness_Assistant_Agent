"""SQLite source-of-truth store for long-term user memories."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence


ALLOWED_MEMORY_KINDS = {
    "rule",
    "fact",
    "preference",
    "todo",
    "goal",
    "constraint",
    "decision",
    "note",
}

ALLOWED_SOURCE_TYPES = {
    "code_rule",
    "user_explicit_remember",
    "llm_candidate",
    "compact_extraction",
    "project_file",
    "manual_import",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_memory_content(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip().lower())


def build_memory_key(user_id: str, kind: str, content: str) -> str:
    normalized = normalize_memory_content(content)
    raw = f"{user_id}:{kind}:{normalized}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def infer_explicit_memory_kind(content: str) -> str:
    if any(word in content for word in ("目标", "想要", "计划")):
        return "goal"
    if any(word in content for word in ("必须", "不能", "不要", "禁忌", "限制")):
        return "constraint"
    if any(word in content for word in ("喜欢", "不喜欢", "偏好", "习惯", "过敏")):
        return "preference"
    return "note"


def infer_privacy_level(content: str) -> str:
    sensitive_markers = (
        "膝盖",
        "腰",
        "肩",
        "旧伤",
        "受伤",
        "疼",
        "痛",
        "疾病",
        "高血压",
        "糖尿病",
        "过敏",
        "手术",
        "康复",
    )
    return "health" if any(marker in content for marker in sensitive_markers) else "normal"


def extract_explicit_memory_content(message: str) -> Optional[str]:
    text = message.strip()
    markers = ("请记住", "帮我记住", "记住一下", "记住")
    for marker in markers:
        if marker in text:
            content = text.split(marker, 1)[1].strip(" ：:，,。.")
            return content or None
    return None


class MemoryStore:
    """Persist long-term memories in SQLite.

    This store is separate from conversation history. It only stores long-term
    user facts/rules/preferences that should survive individual sessions.
    """

    def __init__(
        self,
        db_path: str,
        *,
        semantic_enabled: bool = False,
        semantic_retriever: Any = None,
    ):
        self.db_path = db_path
        self.semantic_enabled = semantic_enabled
        self._semantic_retriever = semantic_retriever
        self._lock = threading.Lock()
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (
                        kind IN ('rule','fact','preference','todo','goal','constraint','decision','note')
                    ),
                    content TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    source_type TEXT NOT NULL CHECK (
                        source_type IN (
                            'code_rule','user_explicit_remember','llm_candidate',
                            'compact_extraction','project_file','manual_import'
                        )
                    ),
                    importance REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','deleted')),
                    access_count INTEGER NOT NULL DEFAULT 0,
                    last_accessed_at TEXT,
                    memory_key TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_items_active_key
                ON memory_items(user_id, memory_key)
                WHERE status = 'active'
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_items_user_status
                ON memory_items(user_id, status, kind, updated_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_sources (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL REFERENCES memory_items(id),
                    source_type TEXT NOT NULL,
                    source_ref TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_relations (
                    id TEXT PRIMARY KEY,
                    from_memory_id TEXT NOT NULL REFERENCES memory_items(id),
                    to_memory_id TEXT NOT NULL REFERENCES memory_items(id),
                    relation_type TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidate_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (
                        kind IN ('rule','fact','preference','todo','goal','constraint','decision','note')
                    ),
                    content TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'global',
                    source_type TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    privacy_level TEXT NOT NULL DEFAULT 'normal',
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','confirmed','rejected')),
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_candidate_memories_user_status
                ON candidate_memories(user_id, status, updated_at)
                """
            )
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts
                    USING fts5(memory_id UNINDEXED, content)
                    """
                )
            except sqlite3.OperationalError:
                # Some embedded SQLite builds omit FTS5. Search falls back to LIKE.
                pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_jobs (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL REFERENCES memory_items(id),
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','completed','failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    next_run_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_embedding_jobs_status
                ON embedding_jobs(status, next_run_at, updated_at)
                """
            )

    def create_memory(
        self,
        *,
        user_id: str,
        kind: str,
        content: str,
        scope: str = "global",
        source_type: str = "manual_import",
        importance: float = 0.5,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._validate_kind(kind)
        self._validate_source_type(source_type)
        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")
        importance = max(0.0, min(1.0, float(importance)))
        memory_id = str(uuid.uuid4())
        memory_key = build_memory_key(user_id, kind, content)
        now = _utc_now()
        metadata_text = json.dumps(dict(metadata or {}), ensure_ascii=False)
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO memory_items (
                        id, user_id, kind, content, scope, source_type, importance,
                        status, access_count, memory_key, metadata, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?)
                    """,
                    (
                        memory_id,
                        user_id,
                        kind,
                        content,
                        scope,
                        source_type,
                        importance,
                        memory_key,
                        metadata_text,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO memory_sources (
                        id, memory_id, source_type, source_ref, metadata, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        memory_id,
                        source_type,
                        None,
                        metadata_text,
                        now,
                    ),
                )
                self._upsert_fts_locked(conn, memory_id, content)
                self._enqueue_embedding_job_locked(conn, memory_id, user_id, now)
            except sqlite3.IntegrityError:
                existing = self._get_by_key_locked(conn, user_id, memory_key)
                if existing is None:
                    raise
                existing["deduplicated"] = True
                return existing
        created = self.get_memory(user_id, memory_id)
        if created is None:
            raise RuntimeError("created memory could not be loaded")
        created["deduplicated"] = False
        return created

    def list_memories(
        self,
        user_id: str,
        *,
        kind: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if kind:
            self._validate_kind(kind)
        limit = max(1, min(int(limit), 200))
        where = ["user_id = ?"]
        params: List[Any] = [user_id]
        if not include_deleted:
            where.append("status = 'active'")
        if kind:
            where.append("kind = ?")
            params.append(kind)
        params.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory_items
                WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_memory(self, user_id: str, memory_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_items
                WHERE id = ? AND user_id = ?
                """,
                (memory_id, user_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update_memory(
        self,
        *,
        user_id: str,
        memory_id: str,
        updates: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        current = self.get_memory(user_id, memory_id)
        if current is None:
            return None

        kind = str(updates.get("kind", current["kind"]))
        self._validate_kind(kind)
        content = str(updates.get("content", current["content"])).strip()
        if not content:
            raise ValueError("content must not be empty")
        source_type = str(updates.get("source_type", current["source_type"]))
        self._validate_source_type(source_type)
        status = str(updates.get("status", current["status"]))
        if status not in {"active", "deleted"}:
            raise ValueError("status must be active or deleted")
        importance = max(0.0, min(1.0, float(updates.get("importance", current["importance"]))))
        scope = str(updates.get("scope", current["scope"]))
        metadata = updates.get("metadata", current["metadata"])
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be an object")
        memory_key = build_memory_key(user_id, kind, content)
        now = _utc_now()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    UPDATE memory_items
                    SET kind = ?, content = ?, scope = ?, source_type = ?,
                        importance = ?, status = ?, memory_key = ?,
                        metadata = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        kind,
                        content,
                        scope,
                        source_type,
                        importance,
                        status,
                        memory_key,
                        json.dumps(dict(metadata), ensure_ascii=False),
                        now,
                        memory_id,
                        user_id,
                    ),
                )
                self._upsert_fts_locked(conn, memory_id, content)
                if status == "active":
                    self._enqueue_embedding_job_locked(conn, memory_id, user_id, now)
            except sqlite3.IntegrityError as exc:
                raise ValueError("active duplicate memory already exists") from exc
        return self.get_memory(user_id, memory_id)

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        now = _utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memory_items
                SET status = 'deleted', updated_at = ?
                WHERE id = ? AND user_id = ? AND status != 'deleted'
                """,
                (now, memory_id, user_id),
            )
            if cursor.rowcount > 0:
                self._delete_fts_locked(conn, memory_id)
            return cursor.rowcount > 0

    def remember_explicit(self, user_id: str, message: str) -> Optional[Dict[str, Any]]:
        content = extract_explicit_memory_content(message)
        if not content:
            return None
        kind = infer_explicit_memory_kind(content)
        privacy_level = infer_privacy_level(content)
        if privacy_level != "normal":
            return self.create_candidate_memory(
                user_id=user_id,
                kind=kind,
                content=content,
                source_type="user_explicit_remember",
                importance=0.8,
                privacy_level=privacy_level,
                metadata={"source_message": message},
            )
        return self.create_memory(
            user_id=user_id,
            kind=kind,
            content=content,
            source_type="user_explicit_remember",
            importance=0.8,
            metadata={"source_message": message},
        )

    def create_candidate_memory(
        self,
        *,
        user_id: str,
        kind: str,
        content: str,
        scope: str = "global",
        source_type: str = "llm_candidate",
        importance: float = 0.5,
        privacy_level: str = "normal",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._validate_kind(kind)
        self._validate_source_type(source_type)
        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")
        candidate_id = str(uuid.uuid4())
        now = _utc_now()
        metadata_text = json.dumps(dict(metadata or {}), ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_memories (
                    id, user_id, kind, content, scope, source_type, importance,
                    privacy_level, status, metadata, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    candidate_id,
                    user_id,
                    kind,
                    content,
                    scope,
                    source_type,
                    max(0.0, min(1.0, float(importance))),
                    privacy_level,
                    metadata_text,
                    now,
                    now,
                ),
            )
        created = self.get_candidate_memory(user_id, candidate_id)
        if created is None:
            raise RuntimeError("created candidate memory could not be loaded")
        created["candidate"] = True
        return created

    def list_candidate_memories(
        self,
        user_id: str,
        *,
        status: str = "pending",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if status not in {"pending", "confirmed", "rejected", "all"}:
            raise ValueError("status must be pending, confirmed, rejected, or all")
        where = ["user_id = ?"]
        params: List[Any] = [user_id]
        if status != "all":
            where.append("status = ?")
            params.append(status)
        params.append(max(1, min(int(limit), 200)))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM candidate_memories
                WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_candidate_memory(
        self,
        user_id: str,
        candidate_id: str,
    ) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM candidate_memories
                WHERE id = ? AND user_id = ?
                """,
                (candidate_id, user_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def confirm_candidate_memory(
        self,
        user_id: str,
        candidate_id: str,
    ) -> Optional[Dict[str, Any]]:
        candidate = self.get_candidate_memory(user_id, candidate_id)
        if candidate is None or candidate["status"] != "pending":
            return None
        memory = self.create_memory(
            user_id=user_id,
            kind=candidate["kind"],
            content=candidate["content"],
            scope=candidate["scope"],
            source_type=candidate["source_type"],
            importance=float(candidate["importance"]),
            metadata={
                **candidate.get("metadata", {}),
                "candidate_id": candidate_id,
                "privacy_level": candidate.get("privacy_level", "normal"),
            },
        )
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE candidate_memories
                SET status = 'confirmed', updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, candidate_id, user_id),
            )
        return memory

    def reject_candidate_memory(self, user_id: str, candidate_id: str) -> bool:
        now = _utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE candidate_memories
                SET status = 'rejected', updated_at = ?
                WHERE id = ? AND user_id = ? AND status = 'pending'
                """,
                (now, candidate_id, user_id),
            )
            return cursor.rowcount > 0

    def search_memories(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        limit = max(1, min(int(limit), 20))
        rows = self._search_fts(user_id, query, limit)
        semantic_rows = self._search_semantic(user_id, query, limit)
        if not rows:
            rows = self._search_like(user_id, query, limit)
        memories = self._merge_search_results(
            [self._row_to_dict(row) for row in rows],
            semantic_rows,
            limit,
        )
        for memory in memories:
            access_bonus = 0.10 * min(int(memory.get("access_count") or 0), 20) / 20
            keyword_score = float(memory.pop("_keyword_score", 0.6))
            embedding_score = float(memory.pop("_embedding_score", 0.0))
            memory["score"] = round(
                (0.45 * max(keyword_score, 0.0))
                + (0.25 * max(embedding_score, 0.0))
                + (0.30 * float(memory.get("importance") or 0.0))
                + access_bonus,
                4,
            )
        memories.sort(key=lambda item: item["score"], reverse=True)
        self._mark_accessed([item["id"] for item in memories])
        return memories

    def process_embedding_jobs(self, *, limit: int = 20) -> Dict[str, Any]:
        if not self.semantic_enabled:
            return {"processed": 0, "completed": 0, "failed": 0, "enabled": False}
        retriever = self._get_semantic_retriever()
        if retriever is None:
            return {"processed": 0, "completed": 0, "failed": 0, "enabled": False}
        jobs = self._load_embedding_jobs(limit=max(1, min(int(limit), 100)))
        completed = 0
        failed = 0
        for job in jobs:
            memory = self.get_memory(job["user_id"], job["memory_id"])
            if not memory or memory.get("status") != "active":
                self._mark_embedding_job(job["id"], "completed")
                completed += 1
                continue
            result = retriever.add_documents(
                [memory["content"]],
                sources=[memory["id"]],
            )
            if result.ok:
                self._mark_embedding_job(job["id"], "completed")
                completed += 1
            else:
                failed += 1
                self._fail_embedding_job(
                    job["id"],
                    int(job["attempts"]) + 1,
                    result.error_message or result.error_code or "unknown",
                )
        return {
            "processed": len(jobs),
            "completed": completed,
            "failed": failed,
            "enabled": True,
        }

    def list_embedding_jobs(
        self,
        *,
        status: str = "pending",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if status not in {"pending", "completed", "failed", "all"}:
            raise ValueError("status must be pending, completed, failed, or all")
        where: List[str] = []
        params: List[Any] = []
        if status != "all":
            where.append("status = ?")
            params.append(status)
        params.append(max(1, min(int(limit), 200)))
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM embedding_jobs
                {clause}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def _get_by_key_locked(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        memory_key: str,
    ) -> Optional[Dict[str, Any]]:
        row = conn.execute(
            """
            SELECT * FROM memory_items
            WHERE user_id = ? AND memory_key = ? AND status = 'active'
            """,
            (user_id, memory_key),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def _search_fts(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> List[sqlite3.Row]:
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT m.*, 1.0 AS _keyword_score
                    FROM memory_items_fts f
                    JOIN memory_items m ON m.id = f.memory_id
                    WHERE memory_items_fts MATCH ?
                      AND m.user_id = ?
                      AND m.status = 'active'
                    ORDER BY m.importance DESC, m.updated_at DESC
                    LIMIT ?
                    """,
                    (query, user_id, limit),
                ).fetchall()
            return list(rows)
        except sqlite3.OperationalError:
            return []

    def _search_like(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> List[sqlite3.Row]:
        terms = self._fallback_like_terms(query)
        if not terms:
            return []
        clauses = " OR ".join("content LIKE ?" for _ in terms)
        params: List[Any] = [user_id] + [f"%{term}%" for term in terms] + [limit]
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *, 0.6 AS _keyword_score
                FROM memory_items
                WHERE user_id = ?
                  AND status = 'active'
                  AND ({clauses})
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return list(rows)

    def _search_semantic(
        self,
        user_id: str,
        query: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not self.semantic_enabled:
            return []
        retriever = self._get_semantic_retriever()
        if retriever is None:
            return []
        try:
            result = retriever.search(query, top_k=limit, threshold=0.1)
        except Exception:
            return []
        if not result.ok or not result.data:
            return []
        found: List[Dict[str, Any]] = []
        for item in result.data:
            memory_id = str(item.get("source") or "")
            if not memory_id:
                continue
            memory = self.get_memory(user_id, memory_id)
            if memory and memory.get("status") == "active":
                memory["_embedding_score"] = float(item.get("score", 0.0))
                found.append(memory)
        return found

    def _merge_search_results(
        self,
        keyword_results: List[Dict[str, Any]],
        semantic_results: Sequence[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for item in keyword_results:
            item.setdefault("_keyword_score", item.get("_keyword_score", 0.6))
            merged[item["id"]] = item
        for item in semantic_results:
            existing = merged.get(item["id"])
            if existing:
                existing["_embedding_score"] = max(
                    float(existing.get("_embedding_score", 0.0)),
                    float(item.get("_embedding_score", 0.0)),
                )
            else:
                item.setdefault("_keyword_score", 0.0)
                merged[item["id"]] = item
        return list(merged.values())[:limit]

    def _fallback_like_terms(self, query: str) -> List[str]:
        query = query.strip()
        if not query:
            return []
        terms = [query]
        terms.extend(part for part in re.split(r"\s+", query) if len(part) >= 2)
        cjk_chars = re.findall(r"[\u4e00-\u9fff]", query)
        cjk_text = "".join(cjk_chars)
        if 2 <= len(cjk_text) <= 60:
            terms.extend(cjk_text[i:i + 2] for i in range(len(cjk_text) - 1))
        deduped: List[str] = []
        for term in terms:
            if term and term not in deduped:
                deduped.append(term)
        return deduped[:30]

    def _mark_accessed(self, memory_ids: List[str]) -> None:
        if not memory_ids:
            return
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                UPDATE memory_items
                SET access_count = access_count + 1,
                    last_accessed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                [(now, now, memory_id) for memory_id in memory_ids],
            )

    def _enqueue_embedding_job_locked(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
        user_id: str,
        now: str,
    ) -> None:
        if not self.semantic_enabled:
            return
        conn.execute(
            """
            INSERT INTO embedding_jobs (
                id, memory_id, user_id, status, attempts, next_run_at,
                created_at, updated_at
            )
            VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)
            """,
            (str(uuid.uuid4()), memory_id, user_id, now, now, now),
        )

    def _load_embedding_jobs(self, *, limit: int) -> List[Dict[str, Any]]:
        now = _utc_now()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM embedding_jobs
                WHERE status IN ('pending','failed')
                  AND attempts < 5
                  AND next_run_at <= ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _mark_embedding_job(self, job_id: str, status: str) -> None:
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE embedding_jobs
                SET status = ?, updated_at = ?, last_error = NULL
                WHERE id = ?
                """,
                (status, now, job_id),
            )

    def _fail_embedding_job(self, job_id: str, attempts: int, error: str) -> None:
        delay_seconds = min(16, 2 ** max(attempts - 1, 0))
        next_run_at = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
        status = "failed"
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE embedding_jobs
                SET status = ?, attempts = ?, last_error = ?,
                    next_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, attempts, error[:500], next_run_at, now, job_id),
            )

    def _upsert_fts_locked(
        self,
        conn: sqlite3.Connection,
        memory_id: str,
        content: str,
    ) -> None:
        try:
            conn.execute("DELETE FROM memory_items_fts WHERE memory_id = ?", (memory_id,))
            conn.execute(
                "INSERT INTO memory_items_fts(memory_id, content) VALUES (?, ?)",
                (memory_id, content),
            )
        except sqlite3.OperationalError:
            pass

    def _delete_fts_locked(self, conn: sqlite3.Connection, memory_id: str) -> None:
        try:
            conn.execute("DELETE FROM memory_items_fts WHERE memory_id = ?", (memory_id,))
        except sqlite3.OperationalError:
            pass

    def _get_semantic_retriever(self):
        if self._semantic_retriever is not None:
            return self._semantic_retriever
        try:
            from app.config import config
            from app.tools.retriever import MilvusRetriever

            self._semantic_retriever = MilvusRetriever(
                uri=config.milvus_uri,
                collection_name=config.memory_milvus_collection_name,
                token=config.milvus_token,
                embedding_model=config.embedding_model,
                index_type=config.milvus_index_type,
                nlist=config.milvus_nlist,
                nprobe=config.milvus_nprobe,
                timeout_seconds=config.milvus_timeout_seconds,
            )
        except Exception:
            self._semantic_retriever = None
        return self._semantic_retriever

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.get("metadata") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["metadata"] = {}
        return item

    def _validate_kind(self, kind: str) -> None:
        if kind not in ALLOWED_MEMORY_KINDS:
            raise ValueError(f"kind must be one of {sorted(ALLOWED_MEMORY_KINDS)}")

    def _validate_source_type(self, source_type: str) -> None:
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}"
            )

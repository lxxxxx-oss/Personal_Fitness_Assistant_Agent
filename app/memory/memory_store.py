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

TASK_KIND_PRIORITY = {
    "diet": {"preference": 1.0, "constraint": 1.0, "fact": 0.8, "goal": 0.7},
    "motion": {"constraint": 1.0, "fact": 0.9, "goal": 0.7, "preference": 0.6},
    "plan": {"goal": 1.0, "constraint": 0.9, "preference": 0.8, "fact": 0.6},
    "general": {},
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
    security_markers = (
        "密码",
        "口令",
        "验证码",
        "token",
        "api key",
        "apikey",
        "身份证",
        "银行卡",
    )
    normalized = content.lower()
    if any(marker in normalized for marker in security_markers):
        return "security"
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


def extract_implicit_memory_content(message: str) -> Optional[str]:
    """Return only stable, user-authored facts suitable for confirmation.

    This intentionally uses conservative lexical evidence. It never treats a
    one-off request as long-term memory and never promotes the result directly.
    """
    text = message.strip()
    if not text or extract_explicit_memory_content(text):
        return None
    transient_markers = ("今天", "这次", "临时", "刚刚", "明天", "本次")
    if any(marker in text for marker in transient_markers):
        return None
    stable_markers = (
        "以后",
        "今后",
        "长期",
        "平时",
        "一直",
        "通常",
        "每周",
        "我习惯",
        "我不吃",
        "我不喜欢",
        "我喜欢",
        "我的目标是",
        "我有",
    )
    return text if any(marker in text for marker in stable_markers) else None


def infer_memory_slot(kind: str, content: str) -> Optional[str]:
    """Infer a conservative conflict slot; ``None`` means coexistence is allowed."""
    if kind == "goal":
        return "primary_fitness_goal"
    if kind in {"preference", "constraint"}:
        categories = {
            "diet_preference": ("吃", "饮食", "香菜", "素食", "过敏"),
            "training_time": ("早上", "上午", "中午", "下午", "晚上", "训练时间"),
            "training_location": ("家里", "健身房", "户外", "训练地点"),
        }
        matches = [
            slot
            for slot, markers in categories.items()
            if any(marker in content for marker in markers)
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def infer_memory_task(query: str) -> str:
    """Infer only the broad task needed to bias memory ranking."""
    task_markers = {
        "diet": ("饮食", "吃", "热量", "蛋白质", "减脂餐", "营养"),
        "motion": ("动作", "深蹲", "卧推", "硬拉", "姿势", "疼", "痛"),
        "plan": ("计划", "安排", "周期", "训练方案", "训练频率"),
    }
    matches = [
        task
        for task, markers in task_markers.items()
        if any(marker in query for marker in markers)
    ]
    return matches[0] if len(matches) == 1 else "general"


def _parse_datetime(value: Optional[str], *, field_name: str) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
            self._ensure_memory_item_columns_locked(conn)
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_observations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    normalized_key TEXT NOT NULL,
                    memory_slot TEXT,
                    risk_level TEXT NOT NULL
                        CHECK (risk_level IN ('low','sensitive','secret')),
                    confidence REAL NOT NULL DEFAULT 0.0,
                    status TEXT NOT NULL DEFAULT 'observed'
                        CHECK (status IN (
                            'observed','review_required','promoted','rejected',
                            'expired','superseded'
                        )),
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    conversation_count INTEGER NOT NULL DEFAULT 0,
                    promoted_memory_id TEXT,
                    expires_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_observations_user_status
                ON memory_observations(user_id, status, updated_at)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_observations_open_key
                ON memory_observations(user_id, normalized_key)
                WHERE status IN ('observed','review_required')
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_evidence (
                    id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL REFERENCES memory_observations(id),
                    conversation_id TEXT,
                    message_id TEXT,
                    source_ref TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    polarity TEXT NOT NULL DEFAULT 'support'
                        CHECK (polarity IN ('support','contradict')),
                    extractor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(observation_id, source_ref)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    reversible INTEGER NOT NULL DEFAULT 0,
                    undone_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_events_user_created
                ON memory_events(user_id, created_at DESC)
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

    @staticmethod
    def _ensure_memory_item_columns_locked(conn: sqlite3.Connection) -> None:
        """Add lifecycle fields without rebuilding existing user databases."""
        existing = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(memory_items)").fetchall()
        }
        additions = {
            "valid_from": "TEXT",
            "expires_at": "TEXT",
            "confidence": "REAL NOT NULL DEFAULT 1.0",
            "superseded_by": "TEXT",
        }
        for column, definition in additions.items():
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE memory_items ADD COLUMN {column} {definition}"
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
        confidence: float = 1.0,
        valid_from: Optional[str] = None,
        expires_at: Optional[str] = None,
        source_ref: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._validate_kind(kind)
        self._validate_source_type(source_type)
        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")
        importance = max(0.0, min(1.0, float(importance)))
        confidence = max(0.0, min(1.0, float(confidence)))
        valid_from_dt = _parse_datetime(valid_from, field_name="valid_from")
        expires_at_dt = _parse_datetime(expires_at, field_name="expires_at")
        if valid_from_dt and expires_at_dt and expires_at_dt <= valid_from_dt:
            raise ValueError("expires_at must be later than valid_from")
        valid_from = valid_from_dt.isoformat() if valid_from_dt else None
        expires_at = expires_at_dt.isoformat() if expires_at_dt else None
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
                        status, access_count, memory_key, metadata, created_at, updated_at,
                        valid_from, expires_at, confidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?, ?, ?, ?)
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
                        valid_from,
                        expires_at,
                        confidence,
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
                        source_ref,
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
            where.append("(valid_from IS NULL OR valid_from <= ?)")
            where.append("(expires_at IS NULL OR expires_at > ?)")
            now = _utc_now()
            params.extend([now, now])
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
        confidence = max(
            0.0,
            min(1.0, float(updates.get("confidence", current.get("confidence", 1.0)))),
        )
        scope = str(updates.get("scope", current["scope"]))
        valid_from_dt = _parse_datetime(
            updates.get("valid_from", current.get("valid_from")),
            field_name="valid_from",
        )
        expires_at_dt = _parse_datetime(
            updates.get("expires_at", current.get("expires_at")),
            field_name="expires_at",
        )
        if valid_from_dt and expires_at_dt and expires_at_dt <= valid_from_dt:
            raise ValueError("expires_at must be later than valid_from")
        valid_from = valid_from_dt.isoformat() if valid_from_dt else None
        expires_at = expires_at_dt.isoformat() if expires_at_dt else None
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
                        metadata = ?, updated_at = ?, confidence = ?,
                        valid_from = ?, expires_at = ?
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
                        confidence,
                        valid_from,
                        expires_at,
                        memory_id,
                        user_id,
                    ),
                )
                if status == "active":
                    self._upsert_fts_locked(conn, memory_id, content)
                    self._enqueue_embedding_job_locked(conn, memory_id, user_id, now)
                else:
                    self._delete_fts_locked(conn, memory_id)
            except sqlite3.IntegrityError as exc:
                raise ValueError("active duplicate memory already exists") from exc
        if status == "deleted":
            self._delete_semantic_sources([memory_id])
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
            deleted = cursor.rowcount > 0
        if deleted:
            self._delete_semantic_sources([memory_id])
        return deleted

    def remember_explicit(self, user_id: str, message: str) -> Optional[Dict[str, Any]]:
        content = extract_explicit_memory_content(message)
        if not content:
            return None
        kind = infer_explicit_memory_kind(content)
        privacy_level = infer_privacy_level(content)
        if privacy_level == "security":
            return None
        slot = infer_memory_slot(kind, content)
        conflicts = self._find_slot_conflicts(user_id, slot, content) if slot else []
        if privacy_level != "normal" or conflicts:
            return self.create_candidate_memory(
                user_id=user_id,
                kind=kind,
                content=content,
                source_type="user_explicit_remember",
                importance=0.8,
                privacy_level=privacy_level,
                metadata={
                    "source_message": message,
                    "memory_slot": slot,
                    "conflicting_memory_ids": [item["id"] for item in conflicts],
                    "candidate_reason": "conflict" if conflicts else "sensitive",
                },
            )
        return self.create_memory(
            user_id=user_id,
            kind=kind,
            content=content,
            source_type="user_explicit_remember",
            importance=0.8,
            metadata={"source_message": message, "memory_slot": slot},
        )

    def remember_user_message(
        self,
        user_id: str,
        message: str,
        *,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Capture explicit memory or a conservative implicit observation.

        Explicit low-risk content may be committed. Implicit low-risk content
        accumulates independent evidence; sensitive content requires review and
        secrets are never persisted.
        """
        explicit = self.remember_explicit(user_id, message)
        if explicit is not None or extract_explicit_memory_content(message):
            return explicit
        content = extract_implicit_memory_content(message)
        if not content or infer_privacy_level(content) == "security":
            return None
        kind = infer_explicit_memory_kind(content)
        slot = infer_memory_slot(kind, content)
        conflicts = self._find_slot_conflicts(user_id, slot, content) if slot else []
        try:
            from app.config import config

            v2_enabled = bool(config.memory_v2_enabled)
        except Exception:
            v2_enabled = True
        if v2_enabled:
            return self.observe_memory(
                user_id=user_id,
                kind=kind,
                content=content,
                conversation_id=conversation_id,
                message_id=message_id,
                has_conflict=bool(conflicts),
                metadata={
                    "source_message": message,
                    "memory_slot": slot,
                    "conflicting_memory_ids": [item["id"] for item in conflicts],
                    "extraction_mode": "conservative_rules",
                },
            )
        return self.create_candidate_memory(
            user_id=user_id,
            kind=kind,
            content=content,
            source_type="llm_candidate",
            importance=0.65,
            privacy_level=infer_privacy_level(content),
            metadata={
                "source_message": message,
                "memory_slot": slot,
                "conflicting_memory_ids": [item["id"] for item in conflicts],
                "candidate_reason": "implicit_stable_fact",
                "extraction_mode": "conservative_rules",
            },
        )

    def observe_memory(
        self,
        *,
        user_id: str,
        kind: str,
        content: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        has_conflict: bool = False,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Record one user-grounded observation and independently sourced evidence."""
        from app.config import config
        from app.memory.models import MemoryRisk
        from app.memory.policy import MemoryPolicy

        self._validate_kind(kind)
        content = content.strip()
        if not content:
            raise ValueError("content must not be empty")
        policy = MemoryPolicy(
            auto_promotion_evidence=config.memory_auto_promotion_evidence,
            auto_promotion_conversations=config.memory_auto_promotion_conversations,
            auto_promotion_confidence=config.memory_auto_promotion_confidence,
            soft_memory_min_confidence=config.memory_soft_min_confidence,
            observation_ttl_days=config.memory_observation_ttl_days,
        )
        risk = policy.risk_for(content)
        if risk is MemoryRisk.SECRET:
            return None
        slot = (metadata or {}).get("memory_slot") or infer_memory_slot(kind, content)
        normalized_key = build_memory_key(
            user_id,
            kind,
            f"{slot or ''}:{normalize_memory_content(content)}",
        )
        now = _utc_now()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=policy.observation_ttl_days)
        ).isoformat()
        source_ref = message_id or (
            f"{conversation_id}:{hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]}"
            if conversation_id
            else f"message:{hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]}"
        )
        evidence_added = False
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_observations
                WHERE user_id = ? AND normalized_key = ?
                  AND status IN ('observed','review_required')
                """,
                (user_id, normalized_key),
            ).fetchone()
            observation_id = str(row["id"]) if row else str(uuid.uuid4())
            if row is None:
                status = (
                    "review_required"
                    if policy.requires_confirmation(risk, has_conflict=has_conflict)
                    else "observed"
                )
                conn.execute(
                    """
                    INSERT INTO memory_observations (
                        id, user_id, kind, content, normalized_key, memory_slot,
                        risk_level, confidence, status, evidence_count,
                        conversation_count, expires_at, metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0, 0, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        user_id,
                        kind,
                        content,
                        normalized_key,
                        slot,
                        risk.value,
                        status,
                        expires_at,
                        json.dumps(dict(metadata or {}), ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO memory_evidence (
                    id, observation_id, conversation_id, message_id, source_ref,
                    snippet, polarity, extractor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'support', 'conservative_rules_v2', ?)
                """,
                (
                    str(uuid.uuid4()),
                    observation_id,
                    conversation_id,
                    message_id,
                    source_ref,
                    content[:500],
                    now,
                ),
            )
            if cursor.rowcount:
                evidence_added = True
                counts = conn.execute(
                    """
                    SELECT COUNT(*) AS evidence_count,
                           COUNT(DISTINCT COALESCE(conversation_id, source_ref))
                               AS conversation_count
                    FROM memory_evidence
                    WHERE observation_id = ? AND polarity = 'support'
                    """,
                    (observation_id,),
                ).fetchone()
                evidence_count = int(counts["evidence_count"])
                conversation_count = int(counts["conversation_count"])
                confidence = min(0.95, 0.68 + 0.14 * (evidence_count - 1))
                conn.execute(
                    """
                    UPDATE memory_observations
                    SET evidence_count = ?, conversation_count = ?,
                        confidence = ?, expires_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        evidence_count,
                        conversation_count,
                        confidence,
                        expires_at,
                        now,
                        observation_id,
                    ),
                )
                self._record_event_locked(
                    conn,
                    user_id=user_id,
                    event_type="capture" if evidence_count == 1 else "reinforce",
                    subject_type="observation",
                    subject_id=observation_id,
                    actor="system",
                    payload={"source_ref": source_ref},
                )
        observation = self.get_observation(user_id, observation_id)
        if observation:
            observation["candidate"] = True
            observation["deduplicated"] = not evidence_added
            observation["privacy_level"] = (
                "health"
                if observation["risk_level"] == "sensitive"
                else observation["risk_level"]
            )
            observation["metadata"] = {
                **observation.get("metadata", {}),
                "candidate_reason": "implicit_stable_fact",
            }
        if (
            observation
            and config.memory_auto_promotion_enabled
            and policy.can_auto_promote(
                risk=risk,
                confidence=float(observation["confidence"]),
                evidence_count=int(observation["evidence_count"]),
                conversation_count=int(observation["conversation_count"]),
                has_conflict=has_conflict,
            )
        ):
            return self.promote_observation(
                user_id, observation_id, actor="system", auto=True
            )
        return observation

    def get_observation(
        self, user_id: str, observation_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM memory_observations WHERE id = ? AND user_id = ?",
                (observation_id, user_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_observations(
        self,
        user_id: str,
        *,
        status: str = "open",
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self.expire_stale_observations(user_id)
        allowed = {
            "open",
            "observed",
            "review_required",
            "promoted",
            "rejected",
            "expired",
            "superseded",
            "all",
        }
        if status not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        where = ["user_id = ?"]
        params: List[Any] = [user_id]
        if status == "open":
            where.append("status IN ('observed','review_required')")
        elif status != "all":
            where.append("status = ?")
            params.append(status)
        params.append(max(1, min(int(limit), 200)))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory_observations
                WHERE {' AND '.join(where)}
                ORDER BY updated_at DESC LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def expire_stale_observations(self, user_id: str) -> int:
        """Expire open observations whose evidence has gone stale."""
        now = _utc_now()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM memory_observations
                WHERE user_id = ? AND status IN ('observed','review_required')
                  AND expires_at IS NOT NULL AND expires_at <= ?
                """,
                (user_id, now),
            ).fetchall()
            for row in rows:
                observation_id = str(row["id"])
                conn.execute(
                    """
                    UPDATE memory_observations
                    SET status = 'expired', updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (now, observation_id, user_id),
                )
                self._record_event_locked(
                    conn,
                    user_id=user_id,
                    event_type="expire",
                    subject_type="observation",
                    subject_id=observation_id,
                    actor="system",
                )
        return len(rows)

    def promote_observation(
        self,
        user_id: str,
        observation_id: str,
        *,
        actor: str = "user",
        auto: bool = False,
    ) -> Optional[Dict[str, Any]]:
        observation = self.get_observation(user_id, observation_id)
        if observation is None or observation["status"] not in {
            "observed",
            "review_required",
        }:
            return None
        if observation["risk_level"] == "secret":
            return None
        memory = self.create_memory(
            user_id=user_id,
            kind=observation["kind"],
            content=observation["content"],
            source_type="llm_candidate",
            importance=0.75 if auto else 0.85,
            confidence=float(observation["confidence"]) if auto else 1.0,
            metadata={
                **observation.get("metadata", {}),
                "observation_id": observation_id,
                "promotion": "automatic" if auto else "confirmed",
            },
        )
        now = _utc_now()
        conflicting_ids = [
            str(item)
            for item in observation.get("metadata", {}).get(
                "conflicting_memory_ids", []
            )
            if item
        ]
        with self._lock, self._connect() as conn:
            for conflicting_id in conflicting_ids:
                cursor = conn.execute(
                    """
                    UPDATE memory_items
                    SET status = 'deleted', superseded_by = ?, updated_at = ?
                    WHERE id = ? AND user_id = ? AND status = 'active'
                    """,
                    (memory["id"], now, conflicting_id, user_id),
                )
                if cursor.rowcount:
                    self._delete_fts_locked(conn, conflicting_id)
                    conn.execute(
                        """
                        INSERT INTO memory_relations (
                            id, from_memory_id, to_memory_id, relation_type,
                            metadata, created_at
                        ) VALUES (?, ?, ?, 'supersedes', '{}', ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            memory["id"],
                            conflicting_id,
                            now,
                        ),
                    )
            conn.execute(
                """
                UPDATE memory_observations
                SET status = 'promoted', promoted_memory_id = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (memory["id"], now, observation_id, user_id),
            )
            self._record_event_locked(
                conn,
                user_id=user_id,
                event_type="promote" if auto else "confirm",
                subject_type="memory",
                subject_id=memory["id"],
                actor=actor,
                payload={"observation_id": observation_id, "auto": auto},
                reversible=True,
            )
        if conflicting_ids:
            self._delete_semantic_sources(conflicting_ids)
        return {**memory, "promoted": True, "automatic": auto}

    def reject_observation(self, user_id: str, observation_id: str) -> bool:
        now = _utc_now()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE memory_observations
                SET status = 'rejected', updated_at = ?
                WHERE id = ? AND user_id = ?
                  AND status IN ('observed','review_required')
                """,
                (now, observation_id, user_id),
            )
            if cursor.rowcount:
                self._record_event_locked(
                    conn,
                    user_id=user_id,
                    event_type="reject",
                    subject_type="observation",
                    subject_id=observation_id,
                    actor="user",
                )
            return cursor.rowcount > 0

    def search_soft_memories(
        self, user_id: str, query: str, *, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Return only low-risk, sufficiently confident, non-expired observations."""
        from app.config import config

        if not config.memory_soft_injection_enabled:
            return []
        self.expire_stale_observations(user_id)
        terms = {
            item
            for item in re.findall(r"[\w\u4e00-\u9fff]{2,}", query.lower())
            if item
        }
        now = _utc_now()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_observations
                WHERE user_id = ? AND status = 'observed' AND risk_level = 'low'
                  AND confidence >= ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY confidence DESC, updated_at DESC LIMIT 100
                """,
                (user_id, config.memory_soft_min_confidence, now),
            ).fetchall()
        ranked = []
        for row in rows:
            item = self._row_to_dict(row)
            content = str(item["content"]).lower()
            overlap = sum(1 for term in terms if term in content)
            item["score"] = float(item["confidence"]) + min(0.15, overlap * 0.05)
            item["uncertain"] = True
            ranked.append(item)
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[: max(1, min(int(limit), 10))]

    def list_memory_events(
        self, user_id: str, *, limit: int = 50
    ) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_events WHERE user_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, max(1, min(int(limit), 200))),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def undo_memory_event(self, user_id: str, event_id: str) -> bool:
        """Undo a promotion by deleting its durable item and reopening observation."""
        now = _utc_now()
        from app.config import config

        refreshed_expiry = (
            datetime.now(timezone.utc)
            + timedelta(days=config.memory_observation_ttl_days)
        ).isoformat()
        with self._lock, self._connect() as conn:
            event = conn.execute(
                """
                SELECT * FROM memory_events
                WHERE id = ? AND user_id = ? AND reversible = 1 AND undone_at IS NULL
                """,
                (event_id, user_id),
            ).fetchone()
            if event is None or event["event_type"] not in {"promote", "confirm"}:
                return False
            payload = json.loads(event["payload"] or "{}")
            memory_id = str(event["subject_id"])
            conn.execute(
                """
                UPDATE memory_items SET status = 'deleted', updated_at = ?
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (now, memory_id, user_id),
            )
            observation_id = payload.get("observation_id")
            if observation_id:
                observation = conn.execute(
                    """
                    SELECT risk_level FROM memory_observations
                    WHERE id = ? AND user_id = ?
                    """,
                    (observation_id, user_id),
                ).fetchone()
                reopened_status = (
                    "review_required"
                    if observation is not None
                    and observation["risk_level"] == "sensitive"
                    else "observed"
                )
                conn.execute(
                    """
                    UPDATE memory_observations
                    SET status = ?, promoted_memory_id = NULL,
                        expires_at = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        reopened_status,
                        refreshed_expiry,
                        now,
                        observation_id,
                        user_id,
                    ),
                )
            conn.execute(
                "UPDATE memory_events SET undone_at = ? WHERE id = ?",
                (now, event_id),
            )
            self._delete_fts_locked(conn, memory_id)
            self._record_event_locked(
                conn,
                user_id=user_id,
                event_type="undo",
                subject_type="event",
                subject_id=event_id,
                actor="user",
                payload={"memory_id": memory_id},
            )
        self._delete_semantic_sources([memory_id])
        return True

    def _record_event_locked(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        event_type: str,
        subject_type: str,
        subject_id: str,
        actor: str,
        payload: Optional[Mapping[str, Any]] = None,
        reversible: bool = False,
    ) -> str:
        event_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO memory_events (
                id, user_id, event_type, subject_type, subject_id, actor,
                payload, reversible, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                user_id,
                event_type,
                subject_type,
                subject_id,
                actor,
                json.dumps(dict(payload or {}), ensure_ascii=False),
                int(reversible),
                _utc_now(),
            ),
        )
        return event_id

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
            existing_rows = conn.execute(
                """
                SELECT * FROM candidate_memories
                WHERE user_id = ? AND kind = ? AND status = 'pending'
                """,
                (user_id, kind),
            ).fetchall()
            normalized = normalize_memory_content(content)
            for row in existing_rows:
                if normalize_memory_content(str(row["content"])) == normalized:
                    existing = self._row_to_dict(row)
                    existing["candidate"] = True
                    existing["deduplicated"] = True
                    return existing
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
        created["deduplicated"] = False
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
        legacy = [self._row_to_dict(row) for row in rows]
        if status in {"pending", "all"}:
            observations = self.list_observations(
                user_id,
                status="open" if status == "pending" else "all",
                limit=limit,
            )
            for item in observations:
                if item["status"] not in {"observed", "review_required"}:
                    continue
                item["candidate"] = True
                item["scope"] = "global"
                item["source_type"] = "llm_candidate"
                item["importance"] = 0.65
                item["privacy_level"] = (
                    "health" if item["risk_level"] == "sensitive" else "normal"
                )
                item["status"] = "pending"
                item["metadata"] = {
                    **item.get("metadata", {}),
                    "candidate_reason": "implicit_stable_fact",
                }
                legacy.append(item)
        legacy.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return legacy[: max(1, min(int(limit), 200))]

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
        if candidate is None:
            return self.promote_observation(user_id, candidate_id, actor="user")
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
        conflicting_ids = [
            str(item)
            for item in candidate.get("metadata", {}).get(
                "conflicting_memory_ids", []
            )
            if item
        ]
        with self._lock, self._connect() as conn:
            for conflicting_id in conflicting_ids:
                cursor = conn.execute(
                    """
                    UPDATE memory_items
                    SET status = 'deleted', superseded_by = ?, updated_at = ?
                    WHERE id = ? AND user_id = ? AND status = 'active'
                    """,
                    (memory["id"], now, conflicting_id, user_id),
                )
                if cursor.rowcount:
                    self._delete_fts_locked(conn, conflicting_id)
                    conn.execute(
                        """
                        INSERT INTO memory_relations (
                            id, from_memory_id, to_memory_id, relation_type,
                            metadata, created_at
                        ) VALUES (?, ?, ?, 'supersedes', '{}', ?)
                        """,
                        (str(uuid.uuid4()), memory["id"], conflicting_id, now),
                    )
            conn.execute(
                """
                UPDATE candidate_memories
                SET status = 'confirmed', updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, candidate_id, user_id),
            )
        self._delete_semantic_sources(conflicting_ids)
        return memory

    def reject_candidate_memory(self, user_id: str, candidate_id: str) -> bool:
        if self.get_candidate_memory(user_id, candidate_id) is None:
            return self.reject_observation(user_id, candidate_id)
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

    def expire_memories(self, *, user_id: Optional[str] = None) -> int:
        """Logically delete memories whose explicit validity window has ended."""
        now = _utc_now()
        where = ["status = 'active'", "expires_at IS NOT NULL", "expires_at <= ?"]
        params: List[Any] = [now]
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM memory_items WHERE {' AND '.join(where)}",
                tuple(params),
            ).fetchall()
            memory_ids = [str(row["id"]) for row in rows]
            if memory_ids:
                placeholders = ",".join("?" for _ in memory_ids)
                conn.execute(
                    f"""
                    UPDATE memory_items
                    SET status = 'deleted', updated_at = ?
                    WHERE id IN ({placeholders})
                    """,
                    (now, *memory_ids),
                )
                for memory_id in memory_ids:
                    self._delete_fts_locked(conn, memory_id)
        self._delete_semantic_sources(memory_ids)
        return len(memory_ids)

    def _find_slot_conflicts(
        self,
        user_id: str,
        slot: str,
        content: str,
    ) -> List[Dict[str, Any]]:
        normalized = normalize_memory_content(content)
        candidates = self.list_memories(user_id, limit=200)
        return [
            item
            for item in candidates
            if item.get("metadata", {}).get("memory_slot") == slot
            and normalize_memory_content(str(item.get("content", ""))) != normalized
        ]

    def search_memories(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 5,
        task_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        limit = max(1, min(int(limit), 20))
        task_type = task_type if task_type in TASK_KIND_PRIORITY else infer_memory_task(query)
        candidate_limit = min(100, max(20, limit * 4))
        rows = self._search_fts(user_id, query, candidate_limit)
        semantic_rows = self._search_semantic(user_id, query, candidate_limit)
        if not rows:
            rows = self._search_like(user_id, query, candidate_limit)
        memories = self._merge_search_results(
            [self._row_to_dict(row) for row in rows],
            semantic_rows,
        )
        for memory in memories:
            access_bonus = 0.02 * min(int(memory.get("access_count") or 0), 20) / 20
            keyword_score = float(memory.pop("_keyword_score", 0.6))
            embedding_score = float(memory.pop("_embedding_score", 0.0))
            task_score = self._task_relevance(memory, task_type)
            memory["score"] = round(
                (0.45 * max(keyword_score, 0.0))
                + (0.25 * max(embedding_score, 0.0))
                + (0.20 * float(memory.get("importance") or 0.0))
                + (0.05 * float(memory.get("confidence") or 0.0))
                + (0.05 * task_score)
                + access_bonus,
                4,
            )
            memory["matched_task"] = task_type
        memories.sort(key=lambda item: item["score"], reverse=True)
        memories = memories[:limit]
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
            now = _utc_now()
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT m.*, 1.0 AS _keyword_score
                    FROM memory_items_fts f
                    JOIN memory_items m ON m.id = f.memory_id
                    WHERE memory_items_fts MATCH ?
                      AND m.user_id = ?
                      AND m.status = 'active'
                      AND (m.valid_from IS NULL OR m.valid_from <= ?)
                      AND (m.expires_at IS NULL OR m.expires_at > ?)
                    ORDER BY m.importance DESC, m.updated_at DESC
                    LIMIT ?
                    """,
                    (query, user_id, now, now, limit),
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
        now = _utc_now()
        params: List[Any] = [user_id, now, now] + [f"%{term}%" for term in terms] + [limit]
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *, 0.6 AS _keyword_score
                FROM memory_items
                WHERE user_id = ?
                  AND status = 'active'
                  AND (valid_from IS NULL OR valid_from <= ?)
                  AND (expires_at IS NULL OR expires_at > ?)
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
            if memory and self._is_memory_current(memory):
                memory["_embedding_score"] = float(item.get("score", 0.0))
                found.append(memory)
        return found

    def _merge_search_results(
        self,
        keyword_results: List[Dict[str, Any]],
        semantic_results: Sequence[Dict[str, Any]],
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
        return list(merged.values())

    @staticmethod
    def _task_relevance(memory: Mapping[str, Any], task_type: str) -> float:
        scope = str(memory.get("scope") or "global")
        if scope == f"task:{task_type}":
            return 1.0
        kind_score = TASK_KIND_PRIORITY.get(task_type, {}).get(
            str(memory.get("kind") or "note"),
            0.4 if task_type != "general" else 0.5,
        )
        return float(kind_score)

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
                    last_accessed_at = ?
                WHERE id = ?
                """,
                [(now, memory_id) for memory_id in memory_ids],
            )

    @staticmethod
    def _is_memory_current(memory: Mapping[str, Any]) -> bool:
        if memory.get("status") != "active":
            return False
        now = datetime.now(timezone.utc)
        valid_from = _parse_datetime(memory.get("valid_from"), field_name="valid_from")
        expires_at = _parse_datetime(memory.get("expires_at"), field_name="expires_at")
        return not ((valid_from and valid_from > now) or (expires_at and expires_at <= now))

    def _delete_semantic_sources(self, memory_ids: Sequence[str]) -> None:
        """Best-effort cleanup; SQLite status remains the authorization boundary."""
        if not memory_ids or not self.semantic_enabled:
            return
        retriever = self._get_semantic_retriever()
        if retriever is None or not hasattr(retriever, "delete_sources"):
            return
        try:
            retriever.delete_sources(list(memory_ids))
        except Exception:
            # Search rechecks SQLite status, so stale vectors cannot be injected.
            return

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
            from app.tools.retriever import SQLiteFaissRetriever

            self._semantic_retriever = SQLiteFaissRetriever(
                db_path=config.memory_vector_db_path,
                embedding_model=config.embedding_model,
                timeout_seconds=config.retriever_timeout_seconds,
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
        if "payload" in item:
            try:
                item["payload"] = json.loads(item.get("payload") or "{}")
            except (TypeError, json.JSONDecodeError):
                item["payload"] = {}
        return item

    def _validate_kind(self, kind: str) -> None:
        if kind not in ALLOWED_MEMORY_KINDS:
            raise ValueError(f"kind must be one of {sorted(ALLOWED_MEMORY_KINDS)}")

    def _validate_source_type(self, source_type: str) -> None:
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError(
                f"source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}"
            )

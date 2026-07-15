"""SQLite-backed conversation persistence for short-term chat recovery."""

from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    """Persist conversations and messages in SQLite.

    This is Phase 1 of the memory optimization roadmap. It deliberately stores
    only conversation history and lightweight session state. Long-term memory
    tables, Memory Writer, FTS5, and Milvus user-memory sync are later phases.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
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
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0,
                    last_compacted_message_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','idle','archived','deleted')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_active_at TEXT NOT NULL,
                    idle_timeout_minutes INTEGER DEFAULT 30
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversations_user_status
                ON conversations(user_id, status, last_active_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user','assistant','system','compact')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('compact','session')),
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','superseded','archived')),
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_states (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    user_id TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create_conversation(self, user_id: str) -> str:
        conversation_id = str(uuid.uuid4())
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations (
                    id, user_id, version, status, created_at, updated_at,
                    last_active_at, idle_timeout_minutes
                )
                VALUES (?, ?, 0, 'active', ?, ?, ?, 30)
                """,
                (conversation_id, user_id, now, now, now),
            )
        return conversation_id

    def get_conversation(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Optional[Dict]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM conversations
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (conversation_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_active_conversation(self, user_id: str) -> Optional[str]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM conversations
                WHERE user_id = ? AND status = 'active'
                ORDER BY last_active_at DESC, created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return str(row["id"]) if row else None

    def get_or_create_conversation(
        self,
        user_id: str,
        conversation_id: Optional[str] = None,
    ) -> str:
        if conversation_id:
            if self.get_conversation(conversation_id, user_id):
                return conversation_id
            raise ValueError("conversation_id was not found for this user")
        latest = self.get_latest_active_conversation(user_id)
        return latest or self.create_conversation(user_id)

    def add_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
    ) -> str:
        message_id = str(uuid.uuid4())
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, user_id, role, content, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, user_id, role, content, now),
            )
            conn.execute(
                """
                UPDATE conversations
                SET version = version + 1,
                    updated_at = ?,
                    last_active_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, now, conversation_id, user_id),
            )
        return message_id

    def add_turn(
        self,
        conversation_id: str,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Persist one complete user/assistant turn in a single transaction."""
        now = _utc_now()
        rows = [
            (str(uuid.uuid4()), conversation_id, user_id, "user", user_msg, now),
            (
                str(uuid.uuid4()),
                conversation_id,
                user_id,
                "assistant",
                assistant_msg,
                now,
            ),
        ]
        with self._lock, self._connect() as conn:
            conversation = conn.execute(
                """
                SELECT id FROM conversations
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (conversation_id, user_id),
            ).fetchone()
            if conversation is None:
                raise ValueError("active conversation was not found for this user")
            conn.executemany(
                """
                INSERT INTO messages (
                    id, conversation_id, user_id, role, content, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.execute(
                """
                UPDATE conversations
                SET version = version + 1,
                    updated_at = ?,
                    last_active_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, now, conversation_id, user_id),
            )

    def get_messages(
        self,
        conversation_id: str,
        user_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        params: tuple = (conversation_id, user_id)
        limit_clause = ""
        if limit is not None and limit > 0:
            limit_clause = "LIMIT ?"
            params = (conversation_id, user_id, int(limit))
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT role, content
                FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY created_at ASC, rowid ASC
                {limit_clause}
                """,
                params,
            ).fetchall()
        return [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in rows
        ]

    def get_message_records(
        self,
        conversation_id: str,
        user_id: str,
    ) -> List[Dict[str, str]]:
        """Return ordered message records including IDs for compact boundaries."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE conversation_id = ? AND user_id = ?
                ORDER BY rowid ASC
                """,
                (conversation_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_active_summary(
        self,
        conversation_id: str,
        user_id: str,
    ) -> Optional[Dict[str, str]]:
        """Return the one active compact summary for an active conversation."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.id, s.content, s.created_at,
                       c.last_compacted_message_id
                FROM summaries AS s
                JOIN conversations AS c ON c.id = s.conversation_id
                WHERE s.conversation_id = ?
                  AND s.user_id = ?
                  AND s.type = 'compact'
                  AND s.status = 'active'
                  AND c.status = 'active'
                ORDER BY s.created_at DESC
                LIMIT 1
                """,
                (conversation_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def get_uncompacted_messages(
        self,
        conversation_id: str,
        user_id: str,
    ) -> List[Dict[str, str]]:
        """Return messages after the current compact boundary, or all messages."""
        records = self.get_message_records(conversation_id, user_id)
        summary = self.get_active_summary(conversation_id, user_id)
        boundary = summary.get("last_compacted_message_id") if summary else None
        if not boundary:
            return records
        for index, record in enumerate(records):
            if record["id"] == boundary:
                return records[index + 1 :]
        return records

    def save_compact_summary(
        self,
        conversation_id: str,
        user_id: str,
        content: str,
        through_message_id: str,
    ) -> Dict[str, str]:
        """Atomically replace the active summary and advance its message boundary."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("summary content must be a non-empty string")
        if not isinstance(through_message_id, str) or not through_message_id.strip():
            raise ValueError("through_message_id must be a non-empty string")

        summary_id = str(uuid.uuid4())
        now = _utc_now()
        with self._lock, self._connect() as conn:
            boundary = conn.execute(
                """
                SELECT m.id
                FROM messages AS m
                JOIN conversations AS c ON c.id = m.conversation_id
                WHERE m.id = ?
                  AND m.conversation_id = ?
                  AND m.user_id = ?
                  AND c.status = 'active'
                """,
                (through_message_id, conversation_id, user_id),
            ).fetchone()
            if boundary is None:
                raise ValueError(
                    "compact boundary message was not found in the active conversation"
                )
            conn.execute(
                """
                UPDATE summaries
                SET status = 'superseded'
                WHERE conversation_id = ?
                  AND user_id = ?
                  AND type = 'compact'
                  AND status = 'active'
                """,
                (conversation_id, user_id),
            )
            conn.execute(
                """
                INSERT INTO summaries (
                    id, conversation_id, user_id, type, content, status, created_at
                )
                VALUES (?, ?, ?, 'compact', ?, 'active', ?)
                """,
                (summary_id, conversation_id, user_id, content.strip(), now),
            )
            conn.execute(
                """
                UPDATE conversations
                SET last_compacted_message_id = ?,
                    version = version + 1,
                    updated_at = ?
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (through_message_id, now, conversation_id, user_id),
            )
        return {
            "id": summary_id,
            "content": content.strip(),
            "last_compacted_message_id": through_message_id,
            "created_at": now,
        }

    def archive_user_conversations(self, user_id: str) -> None:
        now = _utc_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE conversations
                SET status = 'archived',
                    updated_at = ?
                WHERE user_id = ? AND status = 'active'
                """,
                (now, user_id),
            )

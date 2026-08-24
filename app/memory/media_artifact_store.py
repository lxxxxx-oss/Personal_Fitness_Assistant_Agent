"""SQLite persistence for short-lived, ownership-scoped media artifacts.

Only structured analysis results are stored. Raw image/video bytes and pose
keypoint arrays are deliberately excluded to keep the artifact small and to
avoid retaining uploaded biometric media beyond request processing.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


MAX_ARTIFACT_PAYLOAD_BYTES = 128 * 1024
VALID_MEDIA_TYPES = {"image", "video"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _bounded_text(value: str, *, name: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    if len(normalized) > maximum:
        raise ValueError(f"{name} must not exceed {maximum} characters")
    return normalized


class MediaArtifactStore:
    """Persist short-lived Motion analysis summaries with owner isolation."""

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
                CREATE TABLE IF NOT EXISTS media_artifacts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT,
                    media_type TEXT NOT NULL CHECK (media_type IN ('image','video')),
                    filename TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','expired','deleted')),
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    deleted_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_media_artifacts_owner_expiry
                ON media_artifacts(user_id, status, expires_at)
                """
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["payload"] = json.loads(str(item["payload"]))
        return item

    def create_artifact(
        self,
        *,
        user_id: str,
        media_type: str,
        filename: str,
        payload: Dict[str, Any],
        ttl_seconds: int,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create one artifact; callers must not include raw media or keypoints."""
        owner = _bounded_text(user_id, name="user_id", maximum=64)
        kind = _bounded_text(media_type, name="media_type", maximum=16).lower()
        if kind not in VALID_MEDIA_TYPES:
            raise ValueError("media_type must be 'image' or 'video'")
        safe_filename = _bounded_text(filename, name="filename", maximum=255)
        bound_conversation = None
        if conversation_id is not None:
            bound_conversation = _bounded_text(
                conversation_id,
                name="conversation_id",
                maximum=128,
            )
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 86400:
            raise ValueError("ttl_seconds must be between 1 and 86400")

        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > MAX_ARTIFACT_PAYLOAD_BYTES:
            raise ValueError(
                f"payload must not exceed {MAX_ARTIFACT_PAYLOAD_BYTES} bytes"
            )

        artifact_id = str(uuid.uuid4())
        created_at = _utc_now()
        expires_at = created_at + timedelta(seconds=ttl_seconds)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO media_artifacts (
                    id, user_id, conversation_id, media_type, filename, payload,
                    status, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    artifact_id,
                    owner,
                    bound_conversation,
                    kind,
                    safe_filename,
                    serialized,
                    _iso(created_at),
                    _iso(expires_at),
                ),
            )
        item = self.get_artifact(artifact_id, owner)
        if item is None:
            raise RuntimeError("created media artifact could not be reloaded")
        return item

    def get_artifact(
        self,
        artifact_id: str,
        user_id: str,
        *,
        conversation_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return an active owner-visible artifact or ``None``.

        When ``conversation_id`` is supplied, an artifact bound to another
        conversation is hidden. A user-global artifact remains visible.
        """
        artifact = _bounded_text(artifact_id, name="artifact_id", maximum=64)
        owner = _bounded_text(user_id, name="user_id", maximum=64)
        expected_conversation = None
        if conversation_id is not None:
            expected_conversation = _bounded_text(
                conversation_id,
                name="conversation_id",
                maximum=128,
            )

        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM media_artifacts
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (artifact, owner),
            ).fetchone()
            if row is None:
                return None
            if datetime.fromisoformat(str(row["expires_at"])) <= _utc_now():
                conn.execute(
                    """
                    UPDATE media_artifacts SET status = 'expired'
                    WHERE id = ? AND user_id = ? AND status = 'active'
                    """,
                    (artifact, owner),
                )
                return None
            bound_conversation = row["conversation_id"]
            if (
                expected_conversation is not None
                and bound_conversation is not None
                and str(bound_conversation) != expected_conversation
            ):
                return None
        return self._row_to_dict(row)

    def delete_artifact(self, artifact_id: str, user_id: str) -> bool:
        """Soft-delete an active artifact owned by ``user_id``."""
        artifact = _bounded_text(artifact_id, name="artifact_id", maximum=64)
        owner = _bounded_text(user_id, name="user_id", maximum=64)
        now = _iso(_utc_now())
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE media_artifacts
                SET status = 'deleted', deleted_at = ?
                WHERE id = ? AND user_id = ? AND status = 'active'
                  AND expires_at > ?
                """,
                (now, artifact, owner, now),
            )
        return cursor.rowcount == 1

    def purge_expired(self) -> int:
        """Mark all elapsed active artifacts expired and return the count."""
        now = _iso(_utc_now())
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE media_artifacts SET status = 'expired'
                WHERE status = 'active' AND expires_at <= ?
                """,
                (now,),
            )
        return int(cursor.rowcount)

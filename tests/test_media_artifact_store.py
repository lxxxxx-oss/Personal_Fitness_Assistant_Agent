from datetime import datetime, timedelta, timezone

import pytest

from app.memory import media_artifact_store as artifact_module
from app.memory.media_artifact_store import (
    MAX_ARTIFACT_PAYLOAD_BYTES,
    MediaArtifactStore,
)


def test_artifact_owner_conversation_and_delete_boundaries(tmp_path):
    store = MediaArtifactStore(str(tmp_path / "memory.db"))
    artifact = store.create_artifact(
        user_id="alice",
        conversation_id="conversation-a",
        media_type="image",
        filename="pose.jpg",
        payload={"frames": 1, "message": "ok"},
        ttl_seconds=60,
    )

    assert store.get_artifact(
        artifact["id"], "alice", conversation_id="conversation-a"
    )["payload"] == {"frames": 1, "message": "ok"}
    assert store.get_artifact(artifact["id"], "bob") is None
    assert (
        store.get_artifact(
            artifact["id"], "alice", conversation_id="conversation-b"
        )
        is None
    )
    assert store.delete_artifact(artifact["id"], "bob") is False
    assert store.delete_artifact(artifact["id"], "alice") is True
    assert store.get_artifact(artifact["id"], "alice") is None


def test_artifact_expires_lazily(monkeypatch, tmp_path):
    now = {"value": datetime(2026, 8, 20, tzinfo=timezone.utc)}
    monkeypatch.setattr(artifact_module, "_utc_now", lambda: now["value"])
    store = MediaArtifactStore(str(tmp_path / "memory.db"))
    artifact = store.create_artifact(
        user_id="alice",
        media_type="video",
        filename="squat.mp4",
        payload={"frames": 12},
        ttl_seconds=1,
    )

    now["value"] += timedelta(seconds=2)

    assert store.get_artifact(artifact["id"], "alice") is None


def test_artifact_rejects_oversized_structured_payload(tmp_path):
    store = MediaArtifactStore(str(tmp_path / "memory.db"))

    with pytest.raises(ValueError, match="payload must not exceed"):
        store.create_artifact(
            user_id="alice",
            media_type="image",
            filename="pose.jpg",
            payload={"message": "x" * MAX_ARTIFACT_PAYLOAD_BYTES},
            ttl_seconds=60,
        )

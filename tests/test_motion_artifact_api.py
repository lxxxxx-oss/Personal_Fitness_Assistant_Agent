import io

import numpy as np
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.memory.media_artifact_store import MediaArtifactStore
from app.services.motion_analysis import MotionImageAnalysis
from app.tools.pose_sequence import PoseSequence
from app.tools.types import ToolResult


client = TestClient(app)


def _image_analysis() -> MotionImageAnalysis:
    sequence = PoseSequence(
        keypoints=np.zeros((1, 33, 3), dtype=np.float32),
        source_type="image",
        pose_model="mediapipe_pose",
        joint_schema="mediapipe_33",
        confidence=np.ones((1, 33), dtype=np.float32),
    )
    return MotionImageAnalysis(
        sequence=sequence,
        confidence_summary={"mean": 1.0, "min": 1.0, "max": 1.0},
        warnings=[],
        execution_mode="mediapipe_image",
        message="姿态数据已提取。",
    )


def test_image_analysis_can_create_owner_scoped_artifact(monkeypatch, tmp_path):
    store = MediaArtifactStore(str(tmp_path / "memory.db"))
    monkeypatch.setattr(main_module, "_media_artifact_store", store)
    monkeypatch.setattr(
        "app.services.motion_analysis.analyze_motion_image_bytes",
        lambda *args, **kwargs: ToolResult.ok(data=_image_analysis()),
    )

    response = client.post(
        "/motion/analyze-image",
        data={"user_id": "alice"},
        files={"file": ("pose.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["artifact_id"]
    assert body["artifact_expires_at"]

    visible = client.get(
        f"/motion/artifacts/{body['artifact_id']}",
        params={"user_id": "alice"},
    )
    assert visible.status_code == 200
    artifact = visible.json()
    assert artifact["media_type"] == "image"
    assert artifact["payload"]["frames"] == 1
    assert "keypoints" not in artifact["payload"]

    hidden = client.get(
        f"/motion/artifacts/{body['artifact_id']}",
        params={"user_id": "bob"},
    )
    assert hidden.status_code == 404

    deleted = client.delete(
        f"/motion/artifacts/{body['artifact_id']}",
        params={"user_id": "alice"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


def test_analysis_without_user_remains_backward_compatible(monkeypatch):
    monkeypatch.setattr(
        "app.services.motion_analysis.analyze_motion_image_bytes",
        lambda *args, **kwargs: ToolResult.ok(data=_image_analysis()),
    )

    response = client.post(
        "/motion/analyze-image",
        files={"file": ("pose.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["artifact_id"] is None


def test_conversation_binding_requires_owned_active_conversation(monkeypatch, tmp_path):
    from app.memory.conversation_store import ConversationStore

    db_path = str(tmp_path / "memory.db")
    monkeypatch.setattr(main_module, "_conversation_store", ConversationStore(db_path))
    monkeypatch.setattr(main_module, "_media_artifact_store", MediaArtifactStore(db_path))

    response = client.post(
        "/motion/analyze-image",
        data={"user_id": "alice", "conversation_id": "missing"},
        files={"file": ("pose.jpg", io.BytesIO(b"fake-image"), "image/jpeg")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found for this user"

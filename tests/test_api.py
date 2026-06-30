"""FastAPI integration tests."""
import io

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.tools.pose_sequence import PoseSequence
from app.tools.types import ToolResult

client = TestClient(app)


class TestHealthCheck:
    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestChatEndpoint:
    def test_chat_returns_valid_response(self):
        payload = {"user_id": "test_user", "message": "how to squat?"}
        response = client.post("/chat", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "intent" in data
        assert isinstance(data["reply"], str)
        assert len(data["reply"]) > 0

    def test_chat_with_empty_message(self):
        response = client.post("/chat", json={"user_id": "test_user", "message": ""})
        assert response.status_code == 422

    def test_chat_default_intent_is_chat(self):
        payload = {"user_id": "test_user", "message": "hello who are you?"}
        response = client.post("/chat", json=payload)
        data = response.json()
        assert data["intent"] == "chat"

    def test_streaming_endpoint_does_not_generate_final_answer_twice(
        self,
        monkeypatch,
    ):
        from app.llm.loader import LLMLoader

        calls = {"generate": 0, "generate_stream": 0}

        def fake_generate(self, prompt, *args, **kwargs):
            calls["generate"] += 1
            return "duplicate"

        def fake_generate_stream(self, prompt, *args, **kwargs):
            calls["generate_stream"] += 1
            yield "streamed"

        monkeypatch.setattr(LLMLoader, "generate", fake_generate)
        monkeypatch.setattr(LLMLoader, "generate_stream", fake_generate_stream)

        response = client.post(
            "/chat/stream",
            json={"user_id": "stream_user", "message": "你好"},
        )

        assert response.status_code == 200
        assert "streamed" in response.text
        assert calls == {"generate": 0, "generate_stream": 1}


class TestHistoryEndpoint:
    def test_get_history_empty(self):
        response = client.get("/chat/new_user/history")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert data["history"] == []

    def test_delete_history(self):
        response = client.delete("/chat/new_user/history")
        assert response.status_code == 200
        assert response.json()["status"] == "cleared"


class TestMotionAnalyzeEndpoint:
    def test_motion_analyze_accepts_npz_upload(self):
        buffer = io.BytesIO()
        pose = np.random.randn(8, 17, 3).astype(np.float32)
        np.savez(buffer, keypoints=pose)
        buffer.seek(0)

        response = client.post(
            "/motion/analyze",
            files={"file": ("sample.npz", buffer, "application/octet-stream")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "sample.npz"
        assert data["frames"] == 8
        assert data["joints"] == 17
        assert data["metrics"] is None

    def test_motion_analyze_rejects_non_npz_upload(self):
        response = client.post(
            "/motion/analyze",
            files={"file": ("sample.txt", io.BytesIO(b"bad"), "text/plain")},
        )

        assert response.status_code == 422


class TestMotionAnalyzeImageEndpoint:
    def test_motion_analyze_image_returns_static_pose_summary(self, monkeypatch):
        from app.tools import pose_estimator

        def fake_estimate_pose_from_image(image, source_name=None, min_detection_confidence=0.5):
            sequence = PoseSequence(
                keypoints=np.zeros((1, 33, 3), dtype=np.float32),
                source_type="image",
                pose_model="mediapipe_pose",
                joint_schema="mediapipe_33",
                confidence=np.ones((1, 33), dtype=np.float32) * 0.9,
                metadata={"source_name": source_name},
            )
            return ToolResult.ok(data=sequence)

        monkeypatch.setattr(
            pose_estimator,
            "estimate_pose_from_image",
            fake_estimate_pose_from_image,
        )

        buffer = io.BytesIO()
        Image.new("RGB", (8, 6), color=(255, 0, 0)).save(buffer, format="PNG")
        buffer.seek(0)

        response = client.post(
            "/motion/analyze-image",
            files={"file": ("pose.png", buffer, "image/png")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "pose.png"
        assert data["source_type"] == "image"
        assert data["frames"] == 1
        assert data["joints"] == 33
        assert data["pose_model"] == "mediapipe_pose"
        assert data["joint_schema"] == "mediapipe_33"
        assert data["confidence_summary"]["mean"] == 0.9
        assert "静态姿态" in data["message"]
        assert data["warnings"]

    def test_motion_analyze_image_rejects_non_image_suffix(self):
        response = client.post(
            "/motion/analyze-image",
            files={"file": ("pose.txt", io.BytesIO(b"bad"), "text/plain")},
        )

        assert response.status_code == 422

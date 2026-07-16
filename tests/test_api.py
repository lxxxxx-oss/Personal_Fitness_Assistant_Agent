"""FastAPI integration tests."""
import asyncio
import io
import threading

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.tools.pose_sequence import PoseSequence, pose_sequence_to_npz_payload
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
        assert isinstance(data["sources"], list)
        assert isinstance(data["warnings"], list)
        assert isinstance(data["execution"], list)
        assert any(item["component"] == "llm" for item in data["execution"])

    def test_chat_returns_deduplicated_sources_and_warnings(self, monkeypatch):
        import app.main as main_module

        class FakeGraph:
            def invoke(self, state):
                return {
                    "intent": "search",
                    "result": "grounded answer",
                    "_sources": ["https://example.com/a", "https://example.com/a"],
                    "_route_execution_warnings": ["search_degraded", "search_degraded"],
                    "_execution": [
                        {
                            "component": "search",
                            "mode": "mock",
                            "degraded": True,
                            "detail": "demo data",
                        }
                    ],
                }

        monkeypatch.setattr(main_module, "_router_graph", FakeGraph())
        response = client.post(
            "/chat",
            json={"user_id": "metadata_user", "message": "搜索最新资料"},
        )

        assert response.status_code == 200
        assert response.json()["sources"] == ["https://example.com/a"]
        assert response.json()["warnings"] == ["search_degraded"]
        assert response.json()["execution"][0] == {
            "component": "search",
            "mode": "mock",
            "degraded": True,
            "detail": "demo data",
        }

    def test_memory_crud_endpoints(self, monkeypatch, tmp_path):
        import app.main as main_module
        from app.memory.memory_store import MemoryStore

        monkeypatch.setattr(
            main_module,
            "_memory_store",
            MemoryStore(str(tmp_path / "memory.db")),
        )

        create_response = client.post(
            "/memory",
            json={
                "user_id": "memory_api_user",
                "kind": "preference",
                "content": "不喜欢高糖饮料",
                "importance": 0.7,
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["status"] == "active"

        list_response = client.get("/memory", params={"user_id": "memory_api_user"})
        assert list_response.status_code == 200
        assert list_response.json()["memories"][0]["id"] == created["id"]

        patch_response = client.patch(
            f"/memory/{created['id']}",
            json={
                "user_id": "memory_api_user",
                "content": "不喜欢含糖饮料",
            },
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["content"] == "不喜欢含糖饮料"

        delete_response = client.delete(
            f"/memory/{created['id']}",
            params={"user_id": "memory_api_user"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

    def test_memory_search_and_candidate_endpoints(self, monkeypatch, tmp_path):
        import app.main as main_module
        from app.memory.memory_store import MemoryStore

        memory_store = MemoryStore(str(tmp_path / "memory.db"))
        monkeypatch.setattr(main_module, "_memory_store", memory_store)
        memory_store.create_candidate_memory(
            user_id="candidate_api_user",
            kind="note",
            content="我膝盖有旧伤",
            source_type="user_explicit_remember",
            privacy_level="health",
        )

        candidates_response = client.get(
            "/memory/candidates",
            params={"user_id": "candidate_api_user"},
        )
        assert candidates_response.status_code == 200
        candidate = candidates_response.json()["candidates"][0]
        assert candidate["privacy_level"] == "health"

        confirm_response = client.post(
            f"/memory/candidates/{candidate['id']}/confirm",
            params={"user_id": "candidate_api_user"},
        )
        assert confirm_response.status_code == 200
        assert confirm_response.json()["content"] == "我膝盖有旧伤"

        search_response = client.get(
            "/memory/search",
            params={"user_id": "candidate_api_user", "query": "膝盖训练"},
        )
        assert search_response.status_code == 200
        assert search_response.json()["memories"][0]["content"] == "我膝盖有旧伤"

    def test_memory_embedding_job_endpoints(self, monkeypatch, tmp_path):
        import app.main as main_module
        from app.memory.memory_store import MemoryStore
        from tests.test_memory_store import FakeSemanticRetriever

        memory_store = MemoryStore(
            str(tmp_path / "memory.db"),
            semantic_enabled=True,
            semantic_retriever=FakeSemanticRetriever(),
        )
        monkeypatch.setattr(main_module, "_memory_store", memory_store)
        memory_store.create_memory(
            user_id="embedding_api_user",
            kind="goal",
            content="目标是提升卧推力量",
            source_type="manual_import",
        )

        list_response = client.get("/memory/embedding-jobs")
        assert list_response.status_code == 200
        assert list_response.json()["jobs"][0]["status"] == "pending"

        process_response = client.post("/memory/embedding-jobs/process")
        assert process_response.status_code == 200
        assert process_response.json()["completed"] == 1

    def test_chat_explicit_remember_writes_long_term_memory(self, monkeypatch, tmp_path):
        import app.main as main_module
        from app.memory.memory_store import MemoryStore

        memory_store = MemoryStore(str(tmp_path / "memory.db"))
        monkeypatch.setattr(main_module, "_memory_store", memory_store)

        class FakeGraph:
            def invoke(self, state):
                return {"intent": "chat", "result": "我已经记下。"}

        monkeypatch.setattr(main_module, "_router_graph", FakeGraph())
        response = client.post(
            "/chat",
            json={
                "user_id": "remember_api_user",
                "message": "请记住 我不喜欢吃香菜",
            },
        )

        assert response.status_code == 200
        memories = memory_store.list_memories("remember_api_user")
        assert len(memories) == 1
        assert memories[0]["kind"] == "preference"
        assert memories[0]["source_type"] == "user_explicit_remember"

    def test_websocket_meta_returns_sources_and_warnings(self, monkeypatch):
        import app.main as main_module

        class FakeGraph:
            def invoke(self, state):
                return {
                    "intent": "search",
                    "result": "fallback answer",
                    "_sources": ["https://example.com/ws"],
                    "_route_execution_warnings": ["partial_route_failure:diet"],
                    "_execution": [
                        {"component": "search", "mode": "tavily", "degraded": False}
                    ],
                }

        monkeypatch.setattr(main_module, "_router_graph", FakeGraph())
        with client.websocket_connect("/chat/ws") as websocket:
            websocket.send_json({"user_id": "ws_metadata_user", "message": "测试来源"})
            meta = websocket.receive_json()
            assert meta["type"] == "meta"
            assert meta["conversation_id"]
            assert meta["intent"] == "search"
            assert meta["sources"] == ["https://example.com/ws"]
            assert meta["warnings"] == ["partial_route_failure:diet"]
            assert meta["execution"] == [
                {
                    "component": "search",
                    "mode": "tavily",
                    "degraded": False,
                    "detail": "",
                },
                {
                    "component": "llm",
                    "mode": "local_qwen",
                    "degraded": False,
                    "detail": "",
                },
            ]
            assert websocket.receive_json()["type"] == "token"
            assert websocket.receive_json()["type"] == "done"

    @pytest.mark.parametrize(
        "payload",
        [
            {"user_id": "", "message": "hello"},
            {"user_id": "u" * 65, "message": "hello"},
            {"user_id": "valid", "message": ""},
            {"user_id": "valid", "message": "m" * 4097},
            {"user_id": 123, "message": "hello"},
        ],
    )
    def test_websocket_rejects_payloads_outside_http_contract(self, payload):
        with client.websocket_connect("/chat/ws") as websocket:
            websocket.send_json(payload)
            error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["code"] == "INVALID_REQUEST"

    def test_chat_with_empty_message(self):
        response = client.post("/chat", json={"user_id": "test_user", "message": ""})
        assert response.status_code == 422

    def test_chat_default_intent_is_chat(self):
        payload = {"user_id": "test_user", "message": "hello who are you?"}
        response = client.post("/chat", json=payload)
        data = response.json()
        assert data["intent"] == "chat"
        assert data["conversation_id"]

    def test_chat_returns_and_reuses_conversation_id(self):
        first = client.post(
            "/chat",
            json={"user_id": "conversation_user", "message": "hello"},
        )
        assert first.status_code == 200
        conversation_id = first.json()["conversation_id"]

        second = client.post(
            "/chat",
            json={
                "user_id": "conversation_user",
                "conversation_id": conversation_id,
                "message": "continue",
            },
        )

        assert second.status_code == 200
        assert second.json()["conversation_id"] == conversation_id

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
        assert '"sources": []' in response.text
        assert '"warnings": []' in response.text
        assert '"execution":' in response.text
        assert calls == {"generate": 0, "generate_stream": 1}

    def test_sse_token_with_newline_uses_json_framing(self, monkeypatch):
        from app.llm.loader import LLMLoader

        def fake_generate_stream(self, prompt, *args, **kwargs):
            yield "line one\nline two"

        monkeypatch.setattr(LLMLoader, "generate_stream", fake_generate_stream)
        response = client.post(
            "/chat/stream",
            json={"user_id": "sse_newline_user", "message": "hello"},
        )

        assert response.status_code == 200
        assert "event: token" in response.text
        assert 'data: {"text": "line one\\nline two"}' in response.text

    def test_sse_generation_error_is_structured_and_not_persisted(self, monkeypatch):
        from app.llm.loader import LLMGenerationError, LLMLoader
        from app.tools.types import ErrorCode

        client.delete("/chat/sse_error_user/history")

        def fail_generate_stream(self, prompt, *args, **kwargs):
            raise LLMGenerationError(ErrorCode.CONFIG_MISSING, "Model unavailable.")
            yield  # pragma: no cover - keeps this a generator

        monkeypatch.setattr(LLMLoader, "generate_stream", fail_generate_stream)
        response = client.post(
            "/chat/stream",
            json={"user_id": "sse_error_user", "message": "hello"},
        )

        assert response.status_code == 200
        assert "event: error" in response.text
        assert '"code": "CONFIG_MISSING"' in response.text
        assert "Model unavailable." in response.text
        assert client.get("/chat/sse_error_user/history").json()["history"] == []

    def test_websocket_generation_error_is_structured_and_not_persisted(
        self,
        monkeypatch,
    ):
        from app.llm.loader import LLMGenerationError, LLMLoader
        from app.tools.types import ErrorCode

        client.delete("/chat/ws_error_user/history")

        def fail_generate_stream(self, prompt, *args, **kwargs):
            raise LLMGenerationError(ErrorCode.CONFIG_MISSING, "Model unavailable.")
            yield  # pragma: no cover - keeps this a generator

        monkeypatch.setattr(LLMLoader, "generate_stream", fail_generate_stream)
        with client.websocket_connect("/chat/ws") as websocket:
            websocket.send_json({"user_id": "ws_error_user", "message": "hello"})
            assert websocket.receive_json()["type"] == "meta"
            error = websocket.receive_json()

        assert error == {
            "type": "error",
            "code": "CONFIG_MISSING",
            "message": "Model unavailable.",
        }
        assert client.get("/chat/ws_error_user/history").json()["history"] == []

    def test_websocket_forwards_first_token_before_generation_finishes(self):
        from app.main import _stream_llm_to_websocket

        release_second_token = threading.Event()

        class SlowLLM:
            def generate_stream(self, prompt):
                yield "first"
                release_second_token.wait(timeout=2)
                yield "second"

        class FakeWebSocket:
            def __init__(self):
                self.messages = []
                self.first_token_sent = asyncio.Event()

            async def send_json(self, message):
                self.messages.append(message)
                if message.get("text") == "first":
                    self.first_token_sent.set()

        async def scenario():
            websocket = FakeWebSocket()
            stream_task = asyncio.create_task(
                _stream_llm_to_websocket(websocket, SlowLLM(), "prompt")
            )
            try:
                await asyncio.wait_for(websocket.first_token_sent.wait(), timeout=1)
                assert not stream_task.done()
                assert websocket.messages == [{"type": "token", "text": "first"}]
                release_second_token.set()
                reply = await asyncio.wait_for(stream_task, timeout=1)
            finally:
                release_second_token.set()
            assert reply == "firstsecond"
            assert websocket.messages[-1] == {"type": "token", "text": "second"}

        asyncio.run(scenario())

    def test_sync_graph_invocation_does_not_block_event_loop(self):
        from app.main import _invoke_graph

        release_graph = threading.Event()

        class SlowGraph:
            def invoke(self, state):
                release_graph.wait(timeout=2)
                return {**state, "result": "done"}

        async def scenario():
            loop_progressed = asyncio.Event()
            graph_task = asyncio.create_task(
                _invoke_graph(SlowGraph(), {"user_input": "hello"})
            )
            try:
                await asyncio.sleep(0)
                loop_progressed.set()
                await asyncio.wait_for(loop_progressed.wait(), timeout=0.5)
                assert not graph_task.done()
                release_graph.set()
                result = await asyncio.wait_for(graph_task, timeout=1)
            finally:
                release_graph.set()
            assert result["result"] == "done"

        asyncio.run(scenario())


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
        assert data["execution"] == [
            {
                "component": "motion",
                "mode": "mediapipe_image",
                "degraded": False,
                "detail": "",
            }
        ]

    def test_motion_analyze_image_rejects_non_image_suffix(self):
        response = client.post(
            "/motion/analyze-image",
            files={"file": ("pose.txt", io.BytesIO(b"bad"), "text/plain")},
        )

        assert response.status_code == 422

    def test_motion_analyze_image_enforces_server_side_size_limit(self, monkeypatch):
        from app.tools import pose_estimator

        monkeypatch.setattr(pose_estimator, "MAX_IMAGE_BYTES", 8)
        response = client.post(
            "/motion/analyze-image",
            files={"file": ("pose.png", io.BytesIO(b"x" * 9), "image/png")},
        )

        assert response.status_code == 413
        assert "too large" in response.json()["detail"]


class TestMotionAnalyzeVideoEndpoint:
    def test_motion_analyze_video_returns_pose_sequence_summary(self, monkeypatch):
        from app.tools import pose_estimator

        def fake_estimate_pose_from_video_path(path, source_name=None, **kwargs):
            sequence = PoseSequence(
                keypoints=np.zeros((12, 33, 3), dtype=np.float32),
                fps=10.0,
                source_type="video",
                pose_model="mediapipe_pose",
                joint_schema="mediapipe_33",
                confidence=np.ones((12, 33), dtype=np.float32) * 0.9,
                metadata={
                    "sampled_frames": 15,
                    "valid_frames": 12,
                    "valid_frame_ratio": 0.8,
                },
            )
            return ToolResult.ok(data=sequence)

        monkeypatch.setattr(
            pose_estimator,
            "estimate_pose_from_video_path",
            fake_estimate_pose_from_video_path,
        )
        response = client.post(
            "/motion/analyze-video",
            files={"file": ("squat.mp4", io.BytesIO(b"fake-video"), "video/mp4")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source_type"] == "video"
        assert data["frames"] == 12
        assert data["joints"] == 33
        assert data["fps"] == 10.0
        assert data["sampled_frames"] == 15
        assert data["valid_frame_ratio"] == 0.8
        assert data["confidence_summary"]["mean"] == 0.9
        assert data["reference"] is None
        assert data["metrics"] is None
        assert data["execution"] == [
            {
                "component": "motion",
                "mode": "mediapipe_video",
                "degraded": False,
                "detail": "",
            }
        ]

    def test_motion_analyze_video_rejects_unsupported_suffix(self):
        response = client.post(
            "/motion/analyze-video",
            files={"file": ("squat.txt", io.BytesIO(b"bad"), "text/plain")},
        )
        assert response.status_code == 422

    def test_motion_video_compares_with_schema_compatible_reference(
        self,
        monkeypatch,
        tmp_path,
    ):
        from app.config import config
        from app.tools import pose_estimator

        keypoints = np.random.RandomState(7).randn(12, 33, 3).astype(np.float32)
        sequence = PoseSequence(
            keypoints=keypoints,
            fps=10.0,
            source_type="video",
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
            confidence=np.ones((12, 33), dtype=np.float32) * 0.95,
            metadata={
                "sampled_frames": 12,
                "valid_frames": 12,
                "valid_frame_ratio": 1.0,
            },
        )
        reference_path = tmp_path / "squat_standard.npz"
        np.savez_compressed(reference_path, **pose_sequence_to_npz_payload(sequence))
        monkeypatch.setattr(config, "motion_library_dir", str(tmp_path))
        monkeypatch.setattr(
            pose_estimator,
            "estimate_pose_from_video_path",
            lambda *args, **kwargs: ToolResult.ok(data=sequence),
        )

        response = client.post(
            "/motion/analyze-video",
            data={"reference_name": "squat_standard"},
            files={"file": ("squat.mp4", io.BytesIO(b"fake-video"), "video/mp4")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reference"] == "squat_standard"
        assert data["metrics"]["dtw_distance"] == 0.0
        assert data["metrics"]["cosine_similarity"] > 0.99
        assert data["execution"][0]["mode"] == "mediapipe_video_similarity"
        assert "统计接近程度" in data["warnings"][-1]

    def test_motion_video_warns_when_similarity_quality_not_accepted(
        self,
        monkeypatch,
        tmp_path,
    ):
        from app.config import config
        from app.tools import motion_tool, pose_estimator

        sequence = PoseSequence(
            keypoints=np.random.RandomState(11).randn(12, 33, 3).astype(np.float32),
            fps=10.0,
            source_type="video",
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
            confidence=np.ones((12, 33), dtype=np.float32) * 0.95,
            metadata={
                "sampled_frames": 12,
                "valid_frames": 12,
                "valid_frame_ratio": 1.0,
            },
        )
        np.savez_compressed(
            tmp_path / "squat_standard.npz",
            **pose_sequence_to_npz_payload(sequence),
        )
        monkeypatch.setattr(config, "motion_library_dir", str(tmp_path))
        monkeypatch.setattr(
            pose_estimator,
            "estimate_pose_from_video_path",
            lambda *args, **kwargs: ToolResult.ok(data=sequence),
        )
        monkeypatch.setattr(
            motion_tool,
            "compute_pose_sequence_similarity",
            lambda *args, **kwargs: ToolResult.ok(
                data={
                    "dtw_distance": 0.5,
                    "cosine_similarity": 0.8,
                    "shape_difference": 0.2,
                    "quality": {
                        "valid_alignment_ratio": 0.4,
                        "min_valid_alignment_ratio": 0.6,
                        "accepted": False,
                    },
                }
            ),
        )

        response = client.post(
            "/motion/analyze-video",
            data={"reference_name": "squat_standard"},
            files={"file": ("squat.mp4", io.BytesIO(b"fake-video"), "video/mp4")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["metrics"]["quality"]["accepted"] is False
        assert any("低置信参考" in warning for warning in data["warnings"])

    def test_motion_video_rejects_incompatible_reference(
        self,
        monkeypatch,
        tmp_path,
    ):
        from app.config import config
        from app.tools import pose_estimator

        user_sequence = PoseSequence(
            keypoints=np.random.randn(8, 33, 3).astype(np.float32),
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
            metadata={"sampled_frames": 8, "valid_frame_ratio": 1.0},
        )
        np.savez_compressed(
            tmp_path / "legacy_squat.npz",
            keypoints=np.random.randn(8, 17, 3).astype(np.float32),
        )
        monkeypatch.setattr(config, "motion_library_dir", str(tmp_path))
        monkeypatch.setattr(
            pose_estimator,
            "estimate_pose_from_video_path",
            lambda *args, **kwargs: ToolResult.ok(data=user_sequence),
        )

        response = client.post(
            "/motion/analyze-video",
            data={"reference_name": "legacy_squat"},
            files={"file": ("squat.mp4", io.BytesIO(b"fake-video"), "video/mp4")},
        )

        assert response.status_code == 422
        assert "joint_schema mismatch" in response.json()["detail"]

    def test_motion_references_marks_legacy_fixture_incompatible(
        self,
        monkeypatch,
        tmp_path,
    ):
        from app.config import config

        np.savez_compressed(
            tmp_path / "legacy_squat.npz",
            keypoints=np.random.randn(8, 17, 3).astype(np.float32),
        )
        compatible = PoseSequence(
            keypoints=np.random.randn(8, 33, 3).astype(np.float32),
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
        )
        np.savez_compressed(
            tmp_path / "squat_standard.npz",
            **pose_sequence_to_npz_payload(compatible),
        )
        monkeypatch.setattr(config, "motion_library_dir", str(tmp_path))

        response = client.get("/motion/references")

        assert response.status_code == 200
        references = {item["name"]: item for item in response.json()["references"]}
        assert references["legacy_squat"]["compatible_with_video"] is False
        assert references["squat_standard"]["compatible_with_video"] is True
        assert references["squat_standard"]["coordinate_space"] == "unknown"

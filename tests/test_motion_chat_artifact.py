import pytest
from fastapi import HTTPException

import app.main as main_module
from app.api.schemas import ChatRequest
from app.graph.router import intent_classify_node
from app.graph.state import RouterState
from app.graph.subgraphs.motion import check_node, parse_node
from app.memory.media_artifact_store import MediaArtifactStore


def _payload() -> dict:
    return {
        "source_type": "video",
        "frames": 24,
        "joints": 33,
        "pose_model": "mediapipe_pose",
        "joint_schema": "mediapipe_33",
        "valid_frame_ratio": 0.92,
        "confidence_summary": {"mean": 0.88, "min": 0.5, "max": 0.99},
        "reference": "深蹲",
        "metrics": {
            "dtw_distance": 0.21,
            "cosine_similarity": 0.91,
            "shape_difference": 0.13,
            "labels": {"dtw": "优秀", "cosine": "优秀", "shape": "优秀"},
            "overall_verdict": "动作与标准高度一致。",
            "quality": {
                "accepted": True,
                "valid_alignment_ratio": 0.86,
                "min_valid_alignment_ratio": 0.6,
            },
            "joint_distance": {
                "worst_joint": {"joint_index": 25, "mean_distance": 0.18},
                "worst_aligned_point": {
                    "joint_index": 26,
                    "distance": 0.31,
                    "user_frame": 12,
                    "reference_frame": 13,
                    "user_time_seconds": 0.4,
                    "reference_time_seconds": 0.4333,
                },
            },
            "joint_angle_errors": {
                "worst": {
                    "joint": "right_knee",
                    "mean_error_degrees": 8.5,
                    "max_error_degrees": 16.2,
                    "max_error_frame": {
                        "user_frame": 12,
                        "reference_frame": 13,
                        "user_time_seconds": 0.4,
                        "reference_time_seconds": 0.4333,
                    },
                }
            },
        },
        "warnings": ["结果仅作训练参考。"],
    }


def test_chat_request_normalizes_and_limits_motion_artifacts():
    request = ChatRequest(
        user_id="u1",
        message="帮我看看",
        motion_artifact_ids=[" first ", "first", "second"],
    )

    assert request.motion_artifact_ids == ["first", "second"]
    with pytest.raises(ValueError):
        ChatRequest(
            user_id="u1",
            message="帮我看看",
            motion_artifact_ids=["1", "2", "3", "4"],
        )


def test_prepare_chat_resolves_owned_motion_artifact(monkeypatch, tmp_path):
    store = MediaArtifactStore(str(tmp_path / "memory.db"))
    artifact = store.create_artifact(
        user_id="u1",
        media_type="video",
        filename="squat.mp4",
        payload=_payload(),
        ttl_seconds=60,
    )
    monkeypatch.setattr(main_module, "_media_artifact_store", store)
    monkeypatch.setattr(main_module, "_sessions", {})
    monkeypatch.setattr(
        "app.llm.providers.resolve_model_id",
        lambda model_id: model_id or "test-model",
    )

    prepared = main_module._prepare_chat_sync(
        "u1",
        "帮我分析一下",
        None,
        None,
        [artifact["id"]],
        streaming=False,
        temporary=True,
    )

    assert prepared.state["_motion_artifacts"][0]["id"] == artifact["id"]
    assert prepared.state["_motion_artifacts"][0]["payload"]["frames"] == 24


def test_prepare_chat_hides_cross_owner_motion_artifact(monkeypatch, tmp_path):
    store = MediaArtifactStore(str(tmp_path / "memory.db"))
    artifact = store.create_artifact(
        user_id="alice",
        media_type="video",
        filename="squat.mp4",
        payload=_payload(),
        ttl_seconds=60,
    )
    monkeypatch.setattr(main_module, "_media_artifact_store", store)
    monkeypatch.setattr(main_module, "_sessions", {})
    monkeypatch.setattr(
        "app.llm.providers.resolve_model_id",
        lambda model_id: model_id or "test-model",
    )

    with pytest.raises(HTTPException) as exc_info:
        main_module._prepare_chat_sync(
            "bob",
            "帮我分析一下",
            None,
            None,
            [artifact["id"]],
            streaming=False,
            temporary=True,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Motion artifact not found"


def test_motion_artifact_forces_motion_route_for_vague_message():
    state: RouterState = {
        "user_input": "帮我看看这个",
        "user_id": "u1",
        "conversation_id": "c1",
        "memory": [],
        "_motion_artifacts": [{"id": "a1", "payload": _payload()}],
    }

    result = intent_classify_node(state)

    assert result["intent"] == "motion"
    assert result["_route_source"] == "motion_artifact"
    assert result["_route_execution_plan"] == ["motion"]
    assert result["_needs_clarification"] is False


def test_motion_subgraph_uses_structured_artifact_without_raw_media(monkeypatch):
    state: RouterState = {
        "user_input": "指出最需要改进的地方",
        "user_id": "u1",
        "conversation_id": "c1",
        "memory": [],
        "_motion_artifacts": [
            {
                "id": "a1",
                "media_type": "video",
                "filename": "squat.mp4",
                "payload": _payload(),
            }
        ],
        "_streaming": True,
    }
    monkeypatch.setattr(
        "app.tools.motion_tool.list_motion_library",
        lambda *_: type("Result", (), {"ok": True, "data": {}})(),
    )

    parsed = parse_node(state)
    checked = check_node(parsed)

    assert parsed["_tools_to_call"] == []
    assert parsed["_tool_results"][0]["type"] == "media_artifact"
    assert "有效姿态帧比例：0.92" in checked["_prompt"]
    assert "余弦相似度=0.91" in checked["_prompt"]
    assert "平均偏差最大的关节：索引 25" in checked["_prompt"]
    assert "最大单点偏差：关节索引 26，用户帧 12，参考帧 13" in checked["_prompt"]
    assert "最大关节角误差：right_knee，最大 16.2 度" in checked["_prompt"]
    assert "参考时间 0.4333 秒" in checked["_prompt"]
    assert "质量门控：accepted=True" in checked["_prompt"]
    assert checked["result"] == ""


def test_motion_subgraph_without_data_states_current_boundary():
    state: RouterState = {
        "user_input": "帮我分析深蹲动作",
        "user_id": "u1",
        "conversation_id": "c1",
        "memory": [],
        "_tool_results": [],
        "_streaming": True,
    }

    checked = check_node(state)

    assert "可以直接上传图片或视频" in checked["_prompt"]
    assert "尚未实现完整专业动作评分、动作周期切分和专项阶段规则" in checked["_prompt"]
    assert "单动作姿态质量评分" not in checked["_prompt"]
    assert "动作节奏评估" not in checked["_prompt"]
    assert checked["result"] == ""


def test_motion_subgraph_does_not_require_missing_image_comparison_metrics():
    state: RouterState = {
        "user_input": "帮我看看这张深蹲图片",
        "user_id": "u1",
        "conversation_id": "c1",
        "memory": [],
        "_tool_results": [
            {
                "type": "media_artifact",
                "media_type": "image",
                "filename": "squat.jpg",
                "payload": {
                    "frames": 1,
                    "joints": 33,
                    "pose_model": "mediapipe_pose_landmarker_full",
                    "joint_schema": "mediapipe_pose_33",
                    "valid_frame_ratio": 1.0,
                    "metrics": {"cosine_similarity": 0.87},
                },
            }
        ],
        "_streaming": True,
    }

    checked = check_node(state)

    assert "只有结果中存在对比指标时" in checked["_prompt"]
    assert "不得补写缺失指标" in checked["_prompt"]
    assert "三个指标均实际存在" in checked["_prompt"]
    assert "余弦相似度=0.87" in checked["_prompt"]
    assert "DTW=None" not in checked["_prompt"]
    assert "形状差异=None" not in checked["_prompt"]

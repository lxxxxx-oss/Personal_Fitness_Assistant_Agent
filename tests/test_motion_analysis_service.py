import numpy as np

from app.services.motion_analysis import (
    MotionImageAnalysis,
    MotionVideoAnalysis,
    analyze_motion_image_bytes,
    analyze_motion_video_path,
)
from app.tools.pose_sequence import PoseSequence
from app.tools.types import ErrorCode, ToolResult


def _sequence(*, source_type: str, confidence: float = 0.9) -> PoseSequence:
    return PoseSequence(
        keypoints=np.zeros((2, 33, 3), dtype=np.float32),
        fps=10.0 if source_type == "video" else None,
        source_type=source_type,
        pose_model="mediapipe_pose",
        joint_schema="mediapipe_33",
        confidence=np.full((2, 33), confidence, dtype=np.float32),
        metadata={"sampled_frames": 2, "valid_frame_ratio": 1.0},
    )


def test_analyze_motion_image_bytes_returns_structured_result(monkeypatch):
    sequence = _sequence(source_type="image", confidence=0.4)
    monkeypatch.setattr(
        "app.services.motion_analysis.pose_estimator.decode_image_bytes_to_rgb",
        lambda content, filename: ToolResult.ok(data="rgb"),
    )
    monkeypatch.setattr(
        "app.services.motion_analysis.pose_estimator.estimate_pose_from_image",
        lambda image, source_name: ToolResult.ok(data=sequence),
    )

    result = analyze_motion_image_bytes(b"image", filename="pose.jpg")

    assert result.ok
    assert isinstance(result.data, MotionImageAnalysis)
    assert result.data.sequence is sequence
    assert result.data.confidence_summary == {"mean": 0.4, "min": 0.4, "max": 0.4}
    assert any("置信度较低" in warning for warning in result.data.warnings)


def test_analyze_motion_image_bytes_preserves_failure_metadata(monkeypatch):
    monkeypatch.setattr(
        "app.services.motion_analysis.pose_estimator.decode_image_bytes_to_rgb",
        lambda content, filename: ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "bad image",
            decoder="opencv",
        ),
    )

    result = analyze_motion_image_bytes(b"broken", filename="pose.jpg")

    assert not result.ok
    assert result.error_code == ErrorCode.INVALID_PARAM
    assert result.meta == {"decoder": "opencv", "stage": "image_decode"}


def test_analyze_motion_video_path_without_reference(monkeypatch):
    sequence = _sequence(source_type="video")
    monkeypatch.setattr(
        "app.services.motion_analysis.pose_estimator.estimate_pose_from_video_path",
        lambda path, source_name: ToolResult.ok(data=sequence),
    )

    result = analyze_motion_video_path(
        "upload.mp4",
        filename="upload.mp4",
        motion_library_dir="motions",
    )

    assert result.ok
    assert isinstance(result.data, MotionVideoAnalysis)
    assert result.data.sequence is sequence
    assert result.data.sampled_frames == 2
    assert result.data.reference is None
    assert any("未选择标准动作" in warning for warning in result.data.warnings)


def test_analyze_motion_video_path_rejects_unknown_reference(monkeypatch):
    sequence = _sequence(source_type="video")
    monkeypatch.setattr(
        "app.services.motion_analysis.pose_estimator.estimate_pose_from_video_path",
        lambda path, source_name: ToolResult.ok(data=sequence),
    )
    monkeypatch.setattr(
        "app.services.motion_analysis.motion_tool.list_motion_library",
        lambda directory: ToolResult.ok(data={}),
    )

    result = analyze_motion_video_path(
        "upload.mp4",
        filename="upload.mp4",
        motion_library_dir="motions",
        reference_name="squat",
    )

    assert not result.ok
    assert result.error_code == ErrorCode.DATA_NOT_FOUND
    assert result.meta["stage"] == "reference_lookup"

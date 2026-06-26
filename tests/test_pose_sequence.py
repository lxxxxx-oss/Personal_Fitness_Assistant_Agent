"""PoseSequence schema tests."""
import io

import numpy as np

from app.tools.motion_tool import load_npz_pose
from app.tools.pose_sequence import (
    PoseSequence,
    pose_sequence_from_npz,
    pose_sequence_to_npz_payload,
    validate_pose_sequence,
)


def test_validate_pose_sequence_accepts_metadata():
    keypoints = np.random.randn(3, 17, 3).astype(np.float32)
    confidence = np.ones((3, 17), dtype=np.float32)

    result = validate_pose_sequence(
        keypoints,
        fps=30.0,
        source_type="video",
        pose_model="mediapipe_pose",
        joint_schema="mediapipe_33",
        confidence=confidence,
        metadata={"filename": "squat.mp4"},
    )

    assert result.ok
    sequence = result.data
    assert isinstance(sequence, PoseSequence)
    assert sequence.frames == 3
    assert sequence.joints == 17
    assert sequence.coords == 3
    assert sequence.fps == 30.0
    assert sequence.source_type == "video"
    assert result.meta["joint_schema"] == "mediapipe_33"
    assert result.meta["has_confidence"] is True


def test_validate_pose_sequence_rejects_non_numeric_data():
    keypoints = np.array([[["x", "y", "z"], ["a", "b", "c"]]])

    result = validate_pose_sequence(keypoints)

    assert not result.ok
    assert result.error_code == "INVALID_PARAM"
    assert "numeric" in result.error_message


def test_pose_sequence_npz_round_trip_preserves_schema_metadata():
    keypoints = np.random.randn(2, 33, 3).astype(np.float32)
    confidence = np.ones((2, 33), dtype=np.float32)
    sequence = PoseSequence(
        keypoints=keypoints,
        fps=24.0,
        source_type="video",
        pose_model="mediapipe_pose",
        joint_schema="mediapipe_33",
        confidence=confidence,
        metadata={"action": "squat"},
    )

    buffer = io.BytesIO()
    np.savez(buffer, **pose_sequence_to_npz_payload(sequence))
    buffer.seek(0)

    with np.load(buffer) as data:
        result = pose_sequence_from_npz(data)

    assert result.ok
    loaded = result.data
    assert loaded.frames == 2
    assert loaded.joints == 33
    assert loaded.fps == 24.0
    assert loaded.source_type == "video"
    assert loaded.pose_model == "mediapipe_pose"
    assert loaded.joint_schema == "mediapipe_33"
    assert loaded.metadata["action"] == "squat"
    assert np.allclose(loaded.keypoints, keypoints)


def test_load_npz_pose_remains_backward_compatible(tmp_path):
    pose = np.random.randn(4, 17, 3).astype(np.float32)
    path = tmp_path / "legacy_pose_key.npz"
    np.savez(path, pose=pose)

    result = load_npz_pose(str(path))

    assert result.ok
    assert result.data.shape == (4, 17, 3)
    assert result.meta["key"] == "pose"
    assert result.meta["pose_sequence"]["source_type"] == "npz"


def test_load_npz_pose_uses_first_three_coordinates(tmp_path):
    keypoints = np.random.randn(4, 33, 4).astype(np.float32)
    path = tmp_path / "with_visibility.npz"
    np.savez(
        path,
        keypoints=keypoints,
        source_type=np.array("video"),
        pose_model=np.array("mediapipe_pose"),
        joint_schema=np.array("mediapipe_33"),
    )

    result = load_npz_pose(str(path))

    assert result.ok
    assert result.data.shape == (4, 33, 3)
    assert result.meta["pose_sequence"]["coords"] == 4
    assert result.meta["pose_sequence"]["pose_model"] == "mediapipe_pose"

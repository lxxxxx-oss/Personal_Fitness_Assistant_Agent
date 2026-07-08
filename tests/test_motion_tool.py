"""Motion analysis tool tests."""
import numpy as np
import pytest
from app.tools.motion_tool import (
    compute_joint_angles,
    compute_pose_sequence_similarity,
    compute_similarity,
    normalize_pose,
)
from app.tools.pose_sequence import PoseSequence


class TestPoseNormalization:
    def test_normalize_centers_pose_at_origin(self):
        keypoints = np.array([
            [1.0, 1.0, 1.0],
            [2.0, 1.0, 1.0],
            [1.0, 2.0, 1.0],
        ], dtype=np.float32)
        normalized = normalize_pose(keypoints)
        assert abs(normalized[0, 0]) < 1e-5
        assert abs(normalized[0, 1]) < 1e-5
        assert abs(normalized[0, 2]) < 1e-5

    def test_normalize_scales_pose(self):
        keypoints = np.array([
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
        ], dtype=np.float32)
        normalized = normalize_pose(keypoints)
        dist = np.linalg.norm(normalized[1] - normalized[0])
        assert abs(dist - 2.0) < 1e-5

    def test_rejects_invalid_shape(self):
        keypoints = np.array([1.0, 2.0, 3.0])  # 1D
        with pytest.raises(ValueError):
            normalize_pose(keypoints)

    def test_rejects_all_zeros(self):
        keypoints = np.zeros((3, 3))
        with pytest.raises(ValueError):
            normalize_pose(keypoints)

    def test_schema_center_uses_hip_midpoint(self):
        keypoints = np.random.randn(33, 3).astype(np.float32)
        translated = keypoints + np.array([5.0, -3.0, 2.0], dtype=np.float32)

        normalized = normalize_pose(keypoints, center_indices=(23, 24))
        translated_normalized = normalize_pose(translated, center_indices=(23, 24))

        assert np.allclose(normalized, translated_normalized, atol=1e-5)


class TestJointAngles:
    def test_straight_leg_angle_is_pi(self):
        hip = np.array([0.0, 0.0, 0.0])
        knee = np.array([0.0, 1.0, 0.0])
        ankle = np.array([0.0, 2.0, 0.0])
        angle = compute_joint_angles(hip, knee, ankle)
        assert np.isclose(angle, np.pi, atol=1e-3)

    def test_right_angle(self):
        hip = np.array([0.0, 0.0, 0.0])
        knee = np.array([1.0, 0.0, 0.0])
        ankle = np.array([1.0, 1.0, 0.0])
        angle = compute_joint_angles(hip, knee, ankle)
        assert np.isclose(angle, np.pi / 2, atol=1e-4)


class TestSimilarity:
    def test_identical_poses_have_max_similarity(self):
        seq1 = np.random.randn(10, 17, 3).astype(np.float32)
        seq2 = seq1.copy()
        result = compute_similarity(seq1, seq2)
        assert result.ok
        assert result.data["cosine_similarity"] > 0.99
        assert result.data["dtw_distance"] < 0.01
        assert result.data["shape_difference"] < 0.01
        assert "overall_verdict" in result.data
        assert "labels" in result.data
        assert (
            result.meta["shape_difference_definition"]
            == "dtw_aligned_mean_joint_distance"
        )

    def test_shape_difference_uses_aligned_joint_distances(self):
        seq1 = np.array([
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        ], dtype=np.float32)
        seq2 = np.array([
            [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]],
            [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]],
        ], dtype=np.float32)

        result = compute_similarity(seq1, seq2)

        assert result.ok
        assert result.data["shape_difference"] > 0.5

    def test_different_poses_have_lower_similarity(self):
        seq1 = np.ones((10, 17, 3), dtype=np.float32)
        seq2 = np.zeros((10, 17, 3), dtype=np.float32)
        result = compute_similarity(seq1, seq2)
        # All-zero keypoints are rejected — correct behavior
        assert not result.ok
        assert result.error_code == "INTERNAL_ERROR"
        assert "all zeros" in result.error_message.lower() or "all zeros" in result.error_message

    def test_rejects_mismatched_joint_counts(self):
        result = compute_similarity(
            np.random.randn(10, 33, 3).astype(np.float32),
            np.random.randn(10, 17, 3).astype(np.float32),
        )

        assert not result.ok
        assert result.error_code == "INVALID_PARAM"
        assert "same joint count" in result.error_message

    def test_pose_sequence_similarity_requires_matching_schema(self):
        user = PoseSequence(
            keypoints=np.random.randn(10, 33, 3).astype(np.float32),
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
        )
        reference = PoseSequence(
            keypoints=np.random.randn(10, 17, 3).astype(np.float32),
            pose_model="other_model",
            joint_schema="coco_17",
        )

        result = compute_pose_sequence_similarity(user, reference)

        assert not result.ok
        assert result.error_code == "INVALID_PARAM"
        assert "joint_schema mismatch" in result.error_message

    def test_identical_mediapipe_pose_sequences_are_excellent(self):
        keypoints = np.random.randn(12, 33, 3).astype(np.float32)
        user = PoseSequence(
            keypoints=keypoints,
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
        )
        reference = PoseSequence(
            keypoints=keypoints.copy(),
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
        )

        result = compute_pose_sequence_similarity(user, reference)

        assert result.ok
        assert result.data["dtw_distance"] == 0.0
        assert result.data["cosine_similarity"] > 0.99
        assert result.meta["normalization"] == "hip_center_mean_scale"

    def test_pose_sequence_similarity_rejects_coordinate_space_mismatch(self):
        keypoints = np.random.randn(12, 33, 3).astype(np.float32)
        user = PoseSequence(
            keypoints=keypoints,
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
            metadata={"coordinate_space": "world"},
        )
        reference = PoseSequence(
            keypoints=keypoints.copy(),
            pose_model="mediapipe_pose",
            joint_schema="mediapipe_33",
            metadata={"coordinate_space": "normalized_image"},
        )

        result = compute_pose_sequence_similarity(user, reference)

        assert not result.ok
        assert result.error_code == "INVALID_PARAM"
        assert "coordinate_space mismatch" in result.error_message


def test_motion_guidance_without_pose_data_is_visible_as_degraded(monkeypatch, tmp_path):
    from app.config import config
    from app.graph.subgraphs.motion import parse_node

    monkeypatch.setattr(config, "motion_library_dir", str(tmp_path))
    state = {
        "user_input": "帮我分析深蹲姿势",
        "user_id": "u1",
        "intent": "motion",
        "memory": [],
        "result": "",
        "error": None,
    }

    result_state = parse_node(state)

    assert result_state["_execution"] == [
        {
            "component": "motion",
            "mode": "guidance_only",
            "degraded": True,
            "detail": "No uploaded pose data was available",
        }
    ]

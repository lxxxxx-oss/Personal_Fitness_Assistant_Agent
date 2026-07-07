"""Motion analysis tool tests."""
import numpy as np
import pytest
from app.tools.motion_tool import normalize_pose, compute_joint_angles, compute_similarity


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

    def test_different_poses_have_lower_similarity(self):
        seq1 = np.ones((10, 17, 3), dtype=np.float32)
        seq2 = np.zeros((10, 17, 3), dtype=np.float32)
        result = compute_similarity(seq1, seq2)
        # All-zero keypoints are rejected — correct behavior
        assert not result.ok
        assert result.error_code == "INTERNAL_ERROR"
        assert "all zeros" in result.error_message.lower() or "all zeros" in result.error_message


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

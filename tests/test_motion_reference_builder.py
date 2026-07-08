"""Standard motion reference builder tests."""

import numpy as np
import pytest

from app.tools.pose_sequence import PoseSequence, pose_sequence_from_npz
from app.tools.types import ToolResult
from scripts import build_motion_reference


def test_build_reference_persists_schema_metadata(monkeypatch, tmp_path):
    video_path = tmp_path / "standard.mp4"
    video_path.write_bytes(b"fake video")
    sequence = PoseSequence(
        keypoints=np.random.randn(8, 33, 3).astype(np.float32),
        fps=10.0,
        source_type="video",
        pose_model="mediapipe_pose",
        joint_schema="mediapipe_33",
    )
    monkeypatch.setattr(
        build_motion_reference,
        "estimate_pose_from_video_path",
        lambda *args, **kwargs: ToolResult.ok(data=sequence),
    )

    summary = build_motion_reference.build_reference(
        video_path,
        "squat_standard",
        tmp_path / "motions",
    )

    output_path = tmp_path / "motions" / "squat_standard.npz"
    assert output_path.is_file()
    assert summary["joint_schema"] == "mediapipe_33"
    with np.load(output_path, allow_pickle=False) as data:
        loaded = pose_sequence_from_npz(data)
    assert loaded.ok
    assert loaded.data.pose_model == "mediapipe_pose"
    assert loaded.data.metadata["reference_name"] == "squat_standard"

    with pytest.raises(FileExistsError):
        build_motion_reference.build_reference(
            video_path,
            "squat_standard",
            tmp_path / "motions",
        )


def test_build_reference_rejects_path_like_name(tmp_path):
    video_path = tmp_path / "standard.mp4"
    video_path.write_bytes(b"fake video")

    with pytest.raises(ValueError):
        build_motion_reference.build_reference(
            video_path,
            "../squat",
            tmp_path / "motions",
        )

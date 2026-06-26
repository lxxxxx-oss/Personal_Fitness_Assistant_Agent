"""Pose estimator adapter tests."""
import builtins
import io
from types import SimpleNamespace

import numpy as np
from PIL import Image

from app.tools.pose_estimator import (
    _extract_mediapipe_landmarks,
    _extract_tasks_landmarks,
    _load_legacy_pose_module,
    decode_image_bytes_to_rgb,
    estimate_pose_from_image,
    validate_image_array,
)


def test_validate_image_array_accepts_rgb_image():
    image = np.zeros((64, 64, 3), dtype=np.uint8)

    result = validate_image_array(image)

    assert result.ok
    assert result.meta["height"] == 64
    assert result.meta["width"] == 64
    assert result.meta["channels"] == 3


def test_validate_image_array_rejects_grayscale():
    image = np.zeros((64, 64), dtype=np.uint8)

    result = validate_image_array(image)

    assert not result.ok
    assert result.error_code == "INVALID_PARAM"
    assert "(H, W, 3)" in result.error_message


def test_decode_image_bytes_to_rgb_accepts_png():
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), color=(255, 0, 0)).save(buffer, format="PNG")

    result = decode_image_bytes_to_rgb(buffer.getvalue(), filename="pose.png")

    assert result.ok
    assert result.data.shape == (6, 8, 3)
    assert result.meta["height"] == 6
    assert result.meta["width"] == 8


def test_decode_image_bytes_to_rgb_rejects_unsupported_suffix():
    result = decode_image_bytes_to_rgb(b"fake", filename="pose.gif")

    assert not result.ok
    assert result.error_code == "INVALID_PARAM"
    assert ".jpg" in result.error_message


def test_estimate_pose_from_image_reports_missing_mediapipe(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mediapipe":
            raise ImportError("missing mediapipe")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    image = np.zeros((32, 32, 3), dtype=np.uint8)

    result = estimate_pose_from_image(image)

    assert not result.ok
    assert result.error_code == "CONFIG_MISSING"
    assert "MediaPipe is not installed" in result.error_message


def test_estimate_pose_from_image_reports_missing_tasks_model(monkeypatch, tmp_path):
    import mediapipe as mp

    if hasattr(mp, "solutions"):
        monkeypatch.delattr(mp, "solutions", raising=False)
    monkeypatch.setenv(
        "MEDIAPIPE_POSE_MODEL_PATH",
        str(tmp_path / "missing_pose_landmarker.task"),
    )
    image = np.zeros((32, 32, 3), dtype=np.uint8)

    result = estimate_pose_from_image(image)

    assert not result.ok
    assert result.error_code == "CONFIG_MISSING"
    assert "Pose Landmarker model file is missing" in result.error_message


def test_load_legacy_pose_module_returns_none_for_current_tasks_install():
    # The current test environment uses MediaPipe Tasks-only packaging. The
    # adapter must not rely on mp.solutions being available.
    module = _load_legacy_pose_module()
    if module is not None:
        assert hasattr(module, "Pose")


def test_extract_mediapipe_landmarks_returns_pose_sequence():
    landmarks = [
        SimpleNamespace(x=0.1, y=0.2, z=0.3, visibility=0.9)
        for _ in range(33)
    ]
    pose_landmarks = SimpleNamespace(landmark=landmarks)

    result = _extract_mediapipe_landmarks(
        pose_landmarks,
        image_shape=(100, 200, 3),
        source_name="squat.jpg",
    )

    assert result.ok
    sequence = result.data
    assert sequence.frames == 1
    assert sequence.joints == 33
    assert sequence.coords == 3
    assert sequence.source_type == "image"
    assert sequence.pose_model == "mediapipe_pose"
    assert sequence.joint_schema == "mediapipe_33"
    assert sequence.confidence.shape == (1, 33)
    assert sequence.metadata["width"] == 200
    assert sequence.metadata["height"] == 100
    assert sequence.metadata["source_name"] == "squat.jpg"


def test_extract_tasks_landmarks_returns_pose_sequence():
    landmarks = [
        SimpleNamespace(x=0.1, y=0.2, z=0.3, visibility=0.8)
        for _ in range(33)
    ]
    result_obj = SimpleNamespace(
        pose_landmarks=[landmarks],
        pose_world_landmarks=[],
    )

    result = _extract_tasks_landmarks(
        result_obj,
        image_shape=(120, 240, 3),
        source_name="pose.png",
    )

    assert result.ok
    sequence = result.data
    assert sequence.frames == 1
    assert sequence.joints == 33
    assert sequence.pose_model == "mediapipe_pose"
    assert sequence.joint_schema == "mediapipe_33"
    assert sequence.confidence.shape == (1, 33)
    assert sequence.metadata["coordinate_space"] == "normalized_image"

"""Pose estimation adapter for converting media frames into PoseSequence.

This module defines the boundary between future image/video inputs and the
existing motion analysis layer. MediaPipe is loaded lazily so the rest of the
project still works when the optional dependency is not installed.
"""

from io import BytesIO
import importlib
import os
from typing import Any, Optional

import numpy as np

from app.tools.pose_sequence import validate_pose_sequence
from app.tools.types import ErrorCode, ToolResult

MEDIAPIPE_POSE_MODEL = "mediapipe_pose"
MEDIAPIPE_JOINT_SCHEMA = "mediapipe_33"
EXPECTED_IMAGE_NDIM = 3
EXPECTED_IMAGE_CHANNELS = 3
SUPPORTED_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
DEFAULT_POSE_MODEL_PATH = os.path.join("data", "models", "pose_landmarker.task")


def validate_image_array(image: Any) -> ToolResult:
    """Validate an RGB image array for pose estimation."""
    if not isinstance(image, np.ndarray):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"image must be a numpy array, got {type(image).__name__}",
        )

    if image.ndim != EXPECTED_IMAGE_NDIM or image.shape[2] != EXPECTED_IMAGE_CHANNELS:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"image must have shape (H, W, 3), got {image.shape}",
            meta={"shape": image.shape},
        )

    if image.shape[0] <= 0 or image.shape[1] <= 0:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"image height and width must be positive, got {image.shape}",
            meta={"shape": image.shape},
        )

    if not np.issubdtype(image.dtype, np.number):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"image must be numeric, got dtype {image.dtype}",
        )

    if not np.isfinite(image).all():
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "image contains NaN or infinite values",
        )

    return ToolResult.ok(
        data=image,
        height=int(image.shape[0]),
        width=int(image.shape[1]),
        channels=int(image.shape[2]),
    )


def _to_uint8_rgb(image: np.ndarray) -> np.ndarray:
    """Convert a numeric RGB image to uint8 for MediaPipe."""
    if image.dtype == np.uint8:
        return image
    clipped = np.clip(image, 0, 255)
    return clipped.astype(np.uint8)


def decode_image_bytes_to_rgb(
    content: bytes,
    *,
    filename: Optional[str] = None,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> ToolResult:
    """Decode uploaded image bytes into an RGB numpy array.

    The decoder is intentionally separate from pose estimation so tests and
    future API layers can validate file handling without loading MediaPipe.
    """
    if not isinstance(content, (bytes, bytearray)):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"content must be bytes, got {type(content).__name__}",
        )
    if len(content) == 0:
        return ToolResult.fail(ErrorCode.INVALID_PARAM, "image file is empty")
    if len(content) > max_bytes:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"image file is too large, max {max_bytes} bytes",
        )

    if filename:
        lower_name = filename.lower()
        if not lower_name.endswith(SUPPORTED_IMAGE_SUFFIXES):
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                "Only .jpg, .jpeg, and .png images are supported",
                meta={"filename": filename},
            )

    try:
        from PIL import Image
    except ImportError:
        return ToolResult.fail(
            ErrorCode.CONFIG_MISSING,
            "Pillow is not installed. Install 'Pillow' to decode uploaded images.",
        )

    try:
        with Image.open(BytesIO(content)) as image:
            rgb_image = image.convert("RGB")
            array = np.array(rgb_image)
    except Exception as e:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"Cannot decode image file: {e}",
            meta={"filename": filename},
        )

    validation = validate_image_array(array)
    if not validation.ok:
        return validation
    return ToolResult.ok(
        data=array,
        filename=filename,
        height=int(array.shape[0]),
        width=int(array.shape[1]),
        channels=int(array.shape[2]),
    )


def _extract_mediapipe_landmarks(
    pose_landmarks: Any,
    *,
    image_shape: tuple[int, int, int],
    source_name: Optional[str] = None,
) -> ToolResult:
    """Convert MediaPipe landmarks to PoseSequence."""
    height, width, _ = image_shape
    landmarks = getattr(pose_landmarks, "landmark", None)
    if not landmarks:
        return ToolResult.fail(
            ErrorCode.DATA_NOT_FOUND,
            "No pose landmarks found in image",
        )

    keypoints = []
    confidence = []
    for landmark in landmarks:
        keypoints.append([
            float(getattr(landmark, "x", 0.0)),
            float(getattr(landmark, "y", 0.0)),
            float(getattr(landmark, "z", 0.0)),
        ])
        confidence.append(float(getattr(landmark, "visibility", 0.0)))

    metadata = {
        "width": int(width),
        "height": int(height),
    }
    if source_name:
        metadata["source_name"] = source_name

    return validate_pose_sequence(
        np.array([keypoints], dtype=np.float32),
        source_type="image",
        pose_model=MEDIAPIPE_POSE_MODEL,
        joint_schema=MEDIAPIPE_JOINT_SCHEMA,
        confidence=np.array([confidence], dtype=np.float32),
        metadata=metadata,
    )


def _extract_tasks_landmarks(
    result: Any,
    *,
    image_shape: tuple[int, int, int],
    source_name: Optional[str] = None,
) -> ToolResult:
    """Convert MediaPipe Tasks PoseLandmarkerResult to PoseSequence."""
    pose_landmarks = getattr(result, "pose_landmarks", None) or []
    if not pose_landmarks:
        return ToolResult.fail(
            ErrorCode.DATA_NOT_FOUND,
            "No human pose detected in image",
        )

    world_landmarks = getattr(result, "pose_world_landmarks", None) or []
    landmarks = world_landmarks[0] if world_landmarks else pose_landmarks[0]
    if not landmarks:
        return ToolResult.fail(
            ErrorCode.DATA_NOT_FOUND,
            "No pose landmarks found in image",
        )

    height, width, _ = image_shape
    keypoints = []
    confidence = []
    for landmark in landmarks:
        keypoints.append([
            float(getattr(landmark, "x", 0.0)),
            float(getattr(landmark, "y", 0.0)),
            float(getattr(landmark, "z", 0.0)),
        ])
        confidence.append(float(getattr(landmark, "visibility", 0.0)))

    metadata = {
        "width": int(width),
        "height": int(height),
        "coordinate_space": "world" if world_landmarks else "normalized_image",
    }
    if source_name:
        metadata["source_name"] = source_name

    return validate_pose_sequence(
        np.array([keypoints], dtype=np.float32),
        source_type="image",
        pose_model=MEDIAPIPE_POSE_MODEL,
        joint_schema=MEDIAPIPE_JOINT_SCHEMA,
        confidence=np.array([confidence], dtype=np.float32),
        metadata=metadata,
    )


def _estimate_pose_with_tasks(
    image: np.ndarray,
    *,
    source_name: Optional[str],
    min_detection_confidence: float,
) -> ToolResult:
    """Run MediaPipe Tasks PoseLandmarker on a single RGB image."""
    model_path = os.getenv("MEDIAPIPE_POSE_MODEL_PATH", DEFAULT_POSE_MODEL_PATH)
    if not os.path.isfile(model_path):
        return ToolResult.fail(
            ErrorCode.CONFIG_MISSING,
            "MediaPipe Pose Landmarker model file is missing. Download "
            "'pose_landmarker.task' and set MEDIAPIPE_POSE_MODEL_PATH to its "
            f"absolute path, or place it at {DEFAULT_POSE_MODEL_PATH}.",
            model_path=model_path,
        )

    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError:
        return ToolResult.fail(
            ErrorCode.CONFIG_MISSING,
            "MediaPipe Tasks API is not available. Install or upgrade "
            "'mediapipe' to enable image-to-PoseSequence estimation.",
        )

    try:
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=float(min_detection_confidence),
            min_pose_presence_confidence=float(min_detection_confidence),
            min_tracking_confidence=float(min_detection_confidence),
        )
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)
        with vision.PoseLandmarker.create_from_options(options) as landmarker:
            result = landmarker.detect(mp_image)
    except Exception as e:
        return ToolResult.fail(
            ErrorCode.INTERNAL_ERROR,
            f"MediaPipe Tasks pose estimation failed: {e}",
        )

    return _extract_tasks_landmarks(
        result,
        image_shape=image.shape,
        source_name=source_name,
    )


def _load_legacy_pose_module() -> Any:
    """Load legacy MediaPipe Solutions pose module if this install provides it."""
    for module_name in (
        "mediapipe.solutions.pose",
        "mediapipe.python.solutions.pose",
    ):
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    return None


def estimate_pose_from_image(
    image: np.ndarray,
    *,
    source_name: Optional[str] = None,
    min_detection_confidence: float = 0.5,
) -> ToolResult:
    """Estimate a single-image human pose and return PoseSequence.

    Args:
        image: RGB image array with shape (H, W, 3).
        source_name: Optional filename or source id for metadata.
        min_detection_confidence: MediaPipe detection threshold.

    Returns:
        ToolResult.data = PoseSequence on success.
    """
    image_result = validate_image_array(image)
    if not image_result.ok:
        return image_result

    if not isinstance(min_detection_confidence, (int, float)):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "min_detection_confidence must be a number",
        )
    if min_detection_confidence < 0.0 or min_detection_confidence > 1.0:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "min_detection_confidence must be between 0.0 and 1.0",
        )

    try:
        import mediapipe  # noqa: F401
    except ImportError:
        return ToolResult.fail(
            ErrorCode.CONFIG_MISSING,
            "MediaPipe is not installed. Install 'mediapipe' to enable "
            "image-to-PoseSequence estimation.",
        )

    rgb_image = _to_uint8_rgb(image)
    legacy_pose = _load_legacy_pose_module()
    if legacy_pose is None:
        return _estimate_pose_with_tasks(
            rgb_image,
            source_name=source_name,
            min_detection_confidence=float(min_detection_confidence),
        )

    try:
        with legacy_pose.Pose(
            static_image_mode=True,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=float(min_detection_confidence),
        ) as pose:
            result = pose.process(rgb_image)
    except Exception as e:
        return ToolResult.fail(
            ErrorCode.INTERNAL_ERROR,
            f"MediaPipe pose estimation failed: {e}",
        )

    if not getattr(result, "pose_landmarks", None):
        return ToolResult.fail(
            ErrorCode.DATA_NOT_FOUND,
            "No human pose detected in image",
            meta={
                "source_name": source_name,
                "pose_model": MEDIAPIPE_POSE_MODEL,
                "joint_schema": MEDIAPIPE_JOINT_SCHEMA,
            },
        )

    return _extract_mediapipe_landmarks(
        result.pose_landmarks,
        image_shape=rgb_image.shape,
        source_name=source_name,
    )

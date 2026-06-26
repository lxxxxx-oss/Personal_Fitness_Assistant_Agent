"""PoseSequence schema and .npz serialization helpers.

PoseSequence is the internal motion data contract between future media
estimators and the existing motion analysis tools. User-facing uploads may be
images or videos later, but the analysis layer receives validated keypoints.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from app.tools.types import ErrorCode, ToolResult

POSE_SEQUENCE_VERSION = "1.0"
DEFAULT_SOURCE_TYPE = "npz"
DEFAULT_JOINT_SCHEMA = "unknown"
DEFAULT_POSE_MODEL = "unknown"
EXPECTED_NDIM_SEQ = 3
MIN_FRAMES = 1
MIN_KEYPOINTS = 2
MIN_COORDS = 2


@dataclass
class PoseSequence:
    """Validated pose sequence used by the Motion analysis layer.

    Attributes:
        keypoints: Pose array with shape (T, J, C). Current motion analysis
            expects C >= 3 and uses the first three coordinates as x/y/z.
        fps: Optional frame rate. Images or unknown sources may leave it empty.
        source_type: "image", "video", or "npz".
        pose_model: Pose estimator name, for example "mediapipe_pose".
        joint_schema: Keypoint schema, for example "mediapipe_33" or "coco_17".
        confidence: Optional confidence/visibility array aligned with keypoints.
        metadata: Extra non-contract metadata for debugging and evaluation.
    """

    keypoints: np.ndarray
    fps: Optional[float] = None
    source_type: str = DEFAULT_SOURCE_TYPE
    pose_model: str = DEFAULT_POSE_MODEL
    joint_schema: str = DEFAULT_JOINT_SCHEMA
    confidence: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def frames(self) -> int:
        return int(self.keypoints.shape[0])

    @property
    def joints(self) -> int:
        return int(self.keypoints.shape[1])

    @property
    def coords(self) -> int:
        return int(self.keypoints.shape[2])

    def analysis_keypoints(self) -> np.ndarray:
        """Return (T, J, 3) keypoints for the current motion algorithms."""
        if self.coords < 3:
            raise ValueError(
                f"PoseSequence requires at least 3 coordinates for analysis, "
                f"got {self.coords}"
            )
        return self.keypoints[:, :, :3].astype(np.float32)

    def summary(self) -> Dict[str, Any]:
        """Return metadata safe for API responses, docs, and logs."""
        return {
            "version": POSE_SEQUENCE_VERSION,
            "frames": self.frames,
            "joints": self.joints,
            "coords": self.coords,
            "fps": self.fps,
            "source_type": self.source_type,
            "pose_model": self.pose_model,
            "joint_schema": self.joint_schema,
            "has_confidence": self.confidence is not None,
            "metadata": dict(self.metadata),
        }


def _scalar_to_value(value: Any) -> Any:
    """Convert npz scalar arrays to plain Python values."""
    if isinstance(value, np.ndarray) and value.shape == ():
        return value.item()
    return value


def _optional_float(value: Any) -> Optional[float]:
    value = _scalar_to_value(value)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_pose_sequence(
    keypoints: Any,
    *,
    fps: Optional[float] = None,
    source_type: str = DEFAULT_SOURCE_TYPE,
    pose_model: str = DEFAULT_POSE_MODEL,
    joint_schema: str = DEFAULT_JOINT_SCHEMA,
    confidence: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Validate raw pose data and return a PoseSequence.

    This function only validates the shared motion data contract. It does not
    run pose estimation, score exercise quality, or call external services.
    """
    if not isinstance(keypoints, np.ndarray):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"keypoints must be a numpy array, got {type(keypoints).__name__}",
        )

    if keypoints.ndim != EXPECTED_NDIM_SEQ:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"keypoints must have shape (T, J, C), got {keypoints.shape}",
            meta={"shape": keypoints.shape},
        )

    if keypoints.shape[0] < MIN_FRAMES:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"PoseSequence must have at least {MIN_FRAMES} frame, "
            f"got {keypoints.shape[0]}",
            meta={"shape": keypoints.shape},
        )

    if keypoints.shape[1] < MIN_KEYPOINTS:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"PoseSequence must have at least {MIN_KEYPOINTS} keypoints, "
            f"got {keypoints.shape[1]}",
            meta={"shape": keypoints.shape},
        )

    if keypoints.shape[2] < MIN_COORDS:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"PoseSequence must have at least {MIN_COORDS} coordinates, "
            f"got {keypoints.shape[2]}",
            meta={"shape": keypoints.shape},
        )

    if not np.issubdtype(keypoints.dtype, np.number):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"keypoints must be numeric, got dtype {keypoints.dtype}",
        )

    if not np.isfinite(keypoints).all():
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "keypoints contains NaN or infinite values",
        )

    confidence_array = None
    if confidence is not None:
        if not isinstance(confidence, np.ndarray):
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                f"confidence must be a numpy array, got {type(confidence).__name__}",
            )
        if confidence.shape[:2] != keypoints.shape[:2]:
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                "confidence shape must align with keypoints first two "
                f"dimensions, got {confidence.shape} vs {keypoints.shape[:2]}",
            )
        confidence_array = confidence.astype(np.float32)

    sequence = PoseSequence(
        keypoints=keypoints.astype(np.float32),
        fps=fps,
        source_type=str(source_type or DEFAULT_SOURCE_TYPE),
        pose_model=str(pose_model or DEFAULT_POSE_MODEL),
        joint_schema=str(joint_schema or DEFAULT_JOINT_SCHEMA),
        confidence=confidence_array,
        metadata=metadata or {},
    )
    return ToolResult.ok(data=sequence, **sequence.summary())


def pose_sequence_to_npz_payload(sequence: PoseSequence) -> Dict[str, Any]:
    """Return a stable .npz payload for PoseSequence persistence."""
    payload: Dict[str, Any] = {
        "keypoints": sequence.keypoints.astype(np.float32),
        "pose_sequence_version": np.array(POSE_SEQUENCE_VERSION),
        "source_type": np.array(sequence.source_type),
        "pose_model": np.array(sequence.pose_model),
        "joint_schema": np.array(sequence.joint_schema),
    }
    if sequence.fps is not None:
        payload["fps"] = np.array(float(sequence.fps), dtype=np.float32)
    if sequence.confidence is not None:
        payload["confidence"] = sequence.confidence.astype(np.float32)
    for key, value in sequence.metadata.items():
        if isinstance(value, (str, int, float, bool, np.number)):
            payload[f"meta_{key}"] = np.array(value)
    return payload


def pose_sequence_from_npz(npz_data: Any) -> ToolResult:
    """Load PoseSequence from an opened np.load result."""
    keypoints = None
    used_key = None
    for key in ["keypoints", "pose", "positions"]:
        if key in npz_data:
            keypoints = npz_data[key]
            used_key = key
            break
    if keypoints is None and len(npz_data.files) > 0:
        used_key = npz_data.files[0]
        keypoints = npz_data[used_key]

    if keypoints is None:
        return ToolResult.fail(ErrorCode.DATA_NOT_FOUND, "No pose data found")

    metadata = {
        "npz_key": used_key,
        "pose_sequence_version": str(
            _scalar_to_value(
                npz_data["pose_sequence_version"]
                if "pose_sequence_version" in npz_data
                else POSE_SEQUENCE_VERSION
            )
        ),
    }
    for key in npz_data.files:
        if key.startswith("meta_"):
            metadata[key[5:]] = _scalar_to_value(npz_data[key])

    return validate_pose_sequence(
        keypoints,
        fps=_optional_float(npz_data["fps"] if "fps" in npz_data else None),
        source_type=_scalar_to_value(
            npz_data["source_type"] if "source_type" in npz_data else DEFAULT_SOURCE_TYPE
        ),
        pose_model=_scalar_to_value(
            npz_data["pose_model"] if "pose_model" in npz_data else DEFAULT_POSE_MODEL
        ),
        joint_schema=_scalar_to_value(
            npz_data["joint_schema"]
            if "joint_schema" in npz_data
            else DEFAULT_JOINT_SCHEMA
        ),
        confidence=npz_data["confidence"] if "confidence" in npz_data else None,
        metadata=metadata,
    )

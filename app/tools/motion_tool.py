"""3D pose analysis tools — normalization, joint angles, FastDTW, similarity.

PERMISSION: These tools provide quantitative motion metrics for reference only.
They do NOT replace professional coaching, physiotherapy assessment,
or medical diagnosis. Always consult a qualified trainer for exercise form.
Numerical similarity scores are statistical comparisons, not quality guarantees.
"""

import logging
import os
from typing import Dict, Optional, Tuple

import numpy as np

from app.tools.pose_sequence import PoseSequence, pose_sequence_from_npz
from app.tools.types import ToolResult, ErrorCode

logger = logging.getLogger(__name__)

# --- Constants ---
MIN_KEYPOINTS = 2          # Minimum keypoints for a valid pose frame
EXPECTED_DIMS = 3           # x, y, z coordinates
MIN_FRAMES = 1              # Minimum frames for a motion sequence
EXPECTED_NDIM_FRAME = 2     # ndim for a single frame (N, 3)
EXPECTED_NDIM_SEQ = 3       # ndim for a sequence (T, J, 3)

# Similarity thresholds for human-readable labels
DTW_EXCELLENT = 0.3
COS_EXCELLENT = 0.85
SHAPE_EXCELLENT = 0.2


def normalize_pose(
    keypoints: np.ndarray,
    center_indices: Optional[Tuple[int, int]] = None,
) -> np.ndarray:
    """Normalize pose around a configured center and scale to unit size.

    Args:
        keypoints: (N, 3) array for a single frame.
        center_indices: Optional left/right hip indices. Legacy callers use
            keypoint 0 as the center.

    Returns:
        (N, 3) normalized keypoints.

    Raises:
        ValueError: If keypoints has invalid shape or is all-zeros.
    """
    if not isinstance(keypoints, np.ndarray):
        raise ValueError("keypoints must be a numpy array")
    if keypoints.ndim != EXPECTED_NDIM_FRAME or keypoints.shape[1] != EXPECTED_DIMS:
        raise ValueError(
            f"keypoints must have shape (N, 3), got {keypoints.shape}"
        )
    if keypoints.shape[0] < MIN_KEYPOINTS:
        raise ValueError(
            f"keypoints must have at least {MIN_KEYPOINTS} points, "
            f"got {keypoints.shape[0]}"
        )
    if np.allclose(keypoints, 0.0):
        raise ValueError("keypoints is all zeros, cannot normalize")

    if center_indices is None:
        center = keypoints[0].copy()
    else:
        left_index, right_index = center_indices
        if (
            min(left_index, right_index) < 0
            or max(left_index, right_index) >= keypoints.shape[0]
        ):
            raise ValueError(
                f"center_indices {center_indices} exceed {keypoints.shape[0]} keypoints"
            )
        center = (keypoints[left_index] + keypoints[right_index]) / 2.0
    centered = keypoints - center
    distances = np.linalg.norm(centered, axis=1)
    scale = np.mean(distances)
    if scale < 1e-8:
        scale = 1.0
    return centered / scale


def compute_joint_angles(
    p1: np.ndarray, p2: np.ndarray, p3: np.ndarray
) -> float:
    """Compute the angle formed by three points: angle(p1-p2-p3).

    Args:
        p1, p2, p3: (3,) arrays, p2 is the joint center.

    Returns:
        Radians, range [0, π].

    Raises:
        ValueError: If any point has wrong shape.
    """
    for name, pt in [("p1", p1), ("p2", p2), ("p3", p3)]:
        if not isinstance(pt, np.ndarray) or pt.shape != (EXPECTED_DIMS,):
            raise ValueError(
                f"'{name}' must be a numpy array of shape (3,), got "
                f"{getattr(pt, 'shape', type(pt))}"
            )
    v1 = p1 - p2
    v2 = p3 - p2
    denom = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denom < 1e-10:
        return 0.0  # Degenerate: two points coincide
    cos_angle = np.dot(v1, v2) / denom
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.arccos(cos_angle))


def load_npz_pose_sequence(npz_path: str) -> ToolResult:
    """Load a validated PoseSequence while preserving schema metadata.

    Args:
        npz_path: path to .npz file.

    Returns:
        ToolResult with data = PoseSequence on success.
    """
    if not isinstance(npz_path, str) or not npz_path.strip():
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "npz_path must be a non-empty string",
        )

    if not os.path.isfile(npz_path):
        return ToolResult.fail(
            ErrorCode.DATA_NOT_FOUND,
            f"File not found: {npz_path}",
            meta={"path": npz_path},
        )

    try:
        with np.load(npz_path, allow_pickle=False) as data:
            sequence_result = pose_sequence_from_npz(data)
    except Exception as e:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            f"Cannot read .npz file '{npz_path}': {e}",
            meta={"path": npz_path},
        )

    if not sequence_result.ok:
        return ToolResult.fail(
            sequence_result.error_code or ErrorCode.INVALID_PARAM,
            sequence_result.error_message or f"Invalid pose data in '{npz_path}'",
            meta={"path": npz_path, **sequence_result.meta},
        )

    return ToolResult.ok(
        data=sequence_result.data,
        path=npz_path,
        pose_sequence=sequence_result.data.summary(),
    )


def load_npz_pose(npz_path: str) -> ToolResult:
    """Load .npz pose data as the legacy (T, J, 3) analysis array."""
    sequence_result = load_npz_pose_sequence(npz_path)
    if not sequence_result.ok:
        return sequence_result

    sequence = sequence_result.data
    try:
        pose = sequence.analysis_keypoints()
    except ValueError as e:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            str(e),
            meta={"path": npz_path, **sequence_result.meta},
        )

    return ToolResult.ok(
        data=pose,
        path=npz_path,
        key=sequence.metadata.get("npz_key"),
        frames=int(pose.shape[0]),
        joints=int(pose.shape[1]),
        pose_sequence=sequence.summary(),
    )


def compute_similarity(
    seq1: np.ndarray,
    seq2: np.ndarray,
    *,
    center_indices: Optional[Tuple[int, int]] = None,
) -> ToolResult:
    """Compute multi-dimensional similarity between two motion sequences.

    Args:
        seq1: (T1, J, 3) first motion sequence.
        seq2: (T2, J, 3) second motion sequence.

    Returns:
        ToolResult.data = {
            "dtw_distance": float,
            "cosine_similarity": float,
            "shape_difference": float,
            "labels": {
                "dtw": "优秀" | "需改进",
                "cosine": "优秀" | "需改进",
                "shape": "优秀" | "需改进",
            },
            "overall_verdict": str,
        }
    """
    # Input validation
    for name, seq in [("seq1", seq1), ("seq2", seq2)]:
        if not isinstance(seq, np.ndarray):
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                f"'{name}' must be a numpy array, got {type(seq).__name__}",
            )
        if seq.ndim != EXPECTED_NDIM_SEQ:
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                f"'{name}' must have shape (T, J, 3), got {seq.shape}",
            )
    if seq1.shape[1:] != seq2.shape[1:]:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "Motion sequences must use the same joint count and coordinate dimensions, "
            f"got {seq1.shape[1:]} vs {seq2.shape[1:]}",
        )

    try:
        # Normalize each frame
        seq1_norm = np.array([
            normalize_pose(frame, center_indices=center_indices) for frame in seq1
        ])
        seq2_norm = np.array([
            normalize_pose(frame, center_indices=center_indices) for frame in seq2
        ])

        from scipy.spatial.distance import euclidean
        from fastdtw import fastdtw

        flat1 = seq1_norm.reshape(seq1_norm.shape[0], -1)
        flat2 = seq2_norm.reshape(seq2_norm.shape[0], -1)
        dtw_dist, _ = fastdtw(flat1, flat2, dist=euclidean)
        max_len = max(len(flat1), len(flat2))
        dtw_normalized = dtw_dist / max_len

        vec1 = flat1.mean(axis=0)
        vec2 = flat2.mean(axis=0)
        cos_sim = float(
            np.dot(vec1, vec2)
            / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-8)
        )

        shape1 = np.array([np.linalg.norm(frame) for frame in seq1_norm])
        shape2 = np.array([np.linalg.norm(frame) for frame in seq2_norm])
        if len(shape1) != len(shape2):
            target_len = max(len(shape1), len(shape2))
            shape1_interp = np.interp(
                np.linspace(0, 1, target_len),
                np.linspace(0, 1, len(shape1)),
                shape1,
            )
            shape2_interp = np.interp(
                np.linspace(0, 1, target_len),
                np.linspace(0, 1, len(shape2)),
                shape2,
            )
            shape_diff = float(np.mean(np.abs(shape1_interp - shape2_interp)))
        else:
            shape_diff = float(np.mean(np.abs(shape1 - shape2)))
    except Exception as e:
        return ToolResult.fail(
            ErrorCode.INTERNAL_ERROR,
            f"Similarity computation failed: {e}",
        )

    # Human-readable labels
    dtw_label = "优秀" if dtw_normalized < DTW_EXCELLENT else "需改进"
    cos_label = "优秀" if cos_sim > COS_EXCELLENT else "需改进"
    shape_label = "优秀" if shape_diff < SHAPE_EXCELLENT else "需改进"

    all_excellent = all([
        dtw_normalized < DTW_EXCELLENT,
        cos_sim > COS_EXCELLENT,
        shape_diff < SHAPE_EXCELLENT,
    ])
    any_excellent = any([
        dtw_normalized < DTW_EXCELLENT,
        cos_sim > COS_EXCELLENT,
        shape_diff < SHAPE_EXCELLENT,
    ])

    if all_excellent:
        overall = "动作与标准高度一致，三个维度均为优秀。"
    elif any_excellent:
        overall = "部分维度表现优秀，建议关注需改进的维度进行针对性训练。"
    else:
        overall = "动作与标准差异较大，建议在教练指导下调整动作模式。"

    return ToolResult.ok(
        data={
            "dtw_distance": round(dtw_normalized, 4),
            "cosine_similarity": round(cos_sim, 4),
            "shape_difference": round(shape_diff, 4),
            "labels": {
                "dtw": dtw_label,
                "cosine": cos_label,
                "shape": shape_label,
            },
            "overall_verdict": overall,
        },
    )


_SCHEMA_HIP_INDICES: Dict[str, Tuple[int, int]] = {
    "mediapipe_33": (23, 24),
    "coco_17": (11, 12),
}


def compute_pose_sequence_similarity(
    user_sequence: PoseSequence,
    reference_sequence: PoseSequence,
) -> ToolResult:
    """Compare schema-compatible PoseSequence objects using hip-centered metrics."""
    if not isinstance(user_sequence, PoseSequence) or not isinstance(
        reference_sequence, PoseSequence
    ):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "user_sequence and reference_sequence must be PoseSequence objects",
        )
    if user_sequence.joint_schema != reference_sequence.joint_schema:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "PoseSequence joint_schema mismatch: "
            f"{user_sequence.joint_schema} vs {reference_sequence.joint_schema}",
        )
    if user_sequence.pose_model != reference_sequence.pose_model:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "PoseSequence pose_model mismatch: "
            f"{user_sequence.pose_model} vs {reference_sequence.pose_model}",
        )
    center_indices = _SCHEMA_HIP_INDICES.get(user_sequence.joint_schema)
    if center_indices is None:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "Unsupported joint_schema for schema-aware comparison: "
            f"{user_sequence.joint_schema}",
        )
    result = compute_similarity(
        user_sequence.analysis_keypoints(),
        reference_sequence.analysis_keypoints(),
        center_indices=center_indices,
    )
    if result.ok:
        result.meta.update(
            {
                "joint_schema": user_sequence.joint_schema,
                "pose_model": user_sequence.pose_model,
                "normalization": "hip_center_mean_scale",
            }
        )
    return result


def list_motion_library(library_dir: str) -> ToolResult:
    """List all standard motions in the motion library.

    Args:
        library_dir: path to directory containing .npz files.

    Returns:
        ToolResult.data = {motion_name: file_path, ...}
    """
    if not isinstance(library_dir, str) or not library_dir.strip():
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "library_dir must be a non-empty string",
        )

    if not os.path.isdir(library_dir):
        return ToolResult.ok(
            data={},
            note=f"Library directory not found: {library_dir}",
        )

    motions = {}
    for fname in sorted(os.listdir(library_dir)):
        if fname.endswith(".npz"):
            name = os.path.splitext(fname)[0]
            motions[name] = os.path.join(library_dir, fname)

    return ToolResult.ok(
        data=motions,
        count=len(motions),
        library_dir=library_dir,
    )

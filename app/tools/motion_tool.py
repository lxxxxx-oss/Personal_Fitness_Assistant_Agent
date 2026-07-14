"""3D pose analysis tools — normalization, joint angles, FastDTW, similarity.

PERMISSION: These tools provide quantitative motion metrics for reference only.
They do NOT replace professional coaching, physiotherapy assessment,
or medical diagnosis. Always consult a qualified trainer for exercise form.
Numerical similarity scores are statistical comparisons, not quality guarantees.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

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
CONFIDENCE_THRESHOLD = 0.5
MIN_VALID_ALIGNMENT_RATIO = 0.6

MEDIAPIPE_ANGLE_SPECS: Dict[str, Tuple[int, int, int]] = {
    "left_knee": (23, 25, 27),
    "right_knee": (24, 26, 28),
    "left_hip": (11, 23, 25),
    "right_hip": (12, 24, 26),
}


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


def _validate_confidence(
    confidence: Optional[np.ndarray],
    sequence_shape: Tuple[int, int, int],
    name: str,
) -> Optional[np.ndarray]:
    if confidence is None:
        return None
    if not isinstance(confidence, np.ndarray):
        raise ValueError(f"{name} must be a numpy array")
    if confidence.shape[:2] != sequence_shape[:2]:
        raise ValueError(
            f"{name} shape must align with sequence frames/joints, "
            f"got {confidence.shape} vs {sequence_shape[:2]}"
        )
    if not np.isfinite(confidence).all():
        raise ValueError(f"{name} contains NaN or infinite values")
    return confidence.astype(np.float32)


def _confidence_basic_summary(
    confidence: Optional[np.ndarray],
    threshold: float,
) -> Optional[Dict[str, Any]]:
    if confidence is None:
        return None
    return {
        "mean": round(float(confidence.mean()), 4),
        "min": round(float(confidence.min()), 4),
        "max": round(float(confidence.max()), 4),
        "low_confidence_ratio": round(float((confidence < threshold).mean()), 4),
    }


def _alignment_valid_mask(
    alignment_path: List[Tuple[int, int]],
    joint_count: int,
    confidence1: Optional[np.ndarray],
    confidence2: Optional[np.ndarray],
    threshold: float,
) -> np.ndarray:
    mask = np.ones((len(alignment_path), joint_count), dtype=bool)
    if confidence1 is None and confidence2 is None:
        return mask

    for row, (left, right) in enumerate(alignment_path):
        if confidence1 is not None:
            mask[row] &= confidence1[left] >= threshold
        if confidence2 is not None:
            mask[row] &= confidence2[right] >= threshold
    return mask


def _nanmean_or_zero(values: np.ndarray) -> float:
    if values.size == 0 or np.isnan(values).all():
        return 0.0
    return float(np.nanmean(values))


def _joint_distance_diagnostics(
    aligned_joint_distances: np.ndarray,
    valid_mask: np.ndarray,
    fps1: Optional[float],
    fps2: Optional[float],
) -> Dict[str, Any]:
    valid_distances = np.where(valid_mask, aligned_joint_distances, np.nan)
    per_joint_mean = np.zeros(valid_distances.shape[1], dtype=np.float32)
    for joint_index in range(valid_distances.shape[1]):
        joint_values = valid_distances[:, joint_index]
        if not np.isnan(joint_values).all():
            per_joint_mean[joint_index] = float(np.nanmean(joint_values))
    worst_joint_index = int(np.argmax(per_joint_mean))

    if np.isnan(valid_distances).all():
        worst_row = 0
        worst_joint_for_frame = worst_joint_index
        worst_distance = 0.0
    else:
        flat_index = int(np.nanargmax(valid_distances))
        worst_row, worst_joint_for_frame = np.unravel_index(
            flat_index,
            valid_distances.shape,
        )
        worst_distance = float(valid_distances[worst_row, worst_joint_for_frame])

    return {
        "per_joint_mean_distance": [
            round(float(value), 4) for value in per_joint_mean.tolist()
        ],
        "worst_joint": {
            "joint_index": worst_joint_index,
            "mean_distance": round(float(per_joint_mean[worst_joint_index]), 4),
        },
        "worst_aligned_point": {
            "path_index": int(worst_row),
            "joint_index": int(worst_joint_for_frame),
            "distance": round(worst_distance, 4),
            "user_frame": None,
            "reference_frame": None,
            "user_time_seconds": None,
            "reference_time_seconds": None,
        },
    }


def _attach_worst_frame_times(
    diagnostics: Dict[str, Any],
    alignment_path: List[Tuple[int, int]],
    fps1: Optional[float],
    fps2: Optional[float],
) -> None:
    point = diagnostics["worst_aligned_point"]
    path_index = int(point["path_index"])
    if path_index >= len(alignment_path):
        return
    user_frame, reference_frame = alignment_path[path_index]
    point["user_frame"] = int(user_frame)
    point["reference_frame"] = int(reference_frame)
    if fps1 and fps1 > 0:
        point["user_time_seconds"] = round(float(user_frame) / float(fps1), 4)
    if fps2 and fps2 > 0:
        point["reference_time_seconds"] = round(
            float(reference_frame) / float(fps2),
            4,
        )


def _angle_confidence_valid(
    confidence: Optional[np.ndarray],
    frame: int,
    indices: Tuple[int, int, int],
    threshold: float,
) -> bool:
    if confidence is None:
        return True
    return bool(np.all(confidence[frame, list(indices)] >= threshold))


def _joint_angle_error_report(
    seq1: np.ndarray,
    seq2: np.ndarray,
    alignment_path: List[Tuple[int, int]],
    joint_schema: Optional[str],
    confidence1: Optional[np.ndarray],
    confidence2: Optional[np.ndarray],
    threshold: float,
    fps1: Optional[float],
    fps2: Optional[float],
) -> Optional[Dict[str, Any]]:
    if joint_schema != "mediapipe_33" or seq1.shape[1] < 33:
        return None

    joints = []
    worst: Optional[Dict[str, Any]] = None
    for name, indices in MEDIAPIPE_ANGLE_SPECS.items():
        errors: List[float] = []
        max_error = 0.0
        max_pair = (0, 0)
        for left, right in alignment_path:
            if not _angle_confidence_valid(confidence1, left, indices, threshold):
                continue
            if not _angle_confidence_valid(confidence2, right, indices, threshold):
                continue
            angle1 = compute_joint_angles(
                seq1[left, indices[0]],
                seq1[left, indices[1]],
                seq1[left, indices[2]],
            )
            angle2 = compute_joint_angles(
                seq2[right, indices[0]],
                seq2[right, indices[1]],
                seq2[right, indices[2]],
            )
            error = abs(float(np.degrees(angle1 - angle2)))
            errors.append(error)
            if error >= max_error:
                max_error = error
                max_pair = (left, right)

        if errors:
            item = {
                "joint": name,
                "mean_error_degrees": round(float(np.mean(errors)), 2),
                "max_error_degrees": round(float(max_error), 2),
                "valid_pairs": len(errors),
                "max_error_frame": {
                    "user_frame": int(max_pair[0]),
                    "reference_frame": int(max_pair[1]),
                    "user_time_seconds": (
                        round(float(max_pair[0]) / float(fps1), 4)
                        if fps1 and fps1 > 0
                        else None
                    ),
                    "reference_time_seconds": (
                        round(float(max_pair[1]) / float(fps2), 4)
                        if fps2 and fps2 > 0
                        else None
                    ),
                },
            }
            joints.append(item)
            if worst is None or item["max_error_degrees"] > worst["max_error_degrees"]:
                worst = item

    return {
        "unit": "degrees",
        "joint_schema": joint_schema,
        "joints": joints,
        "worst": worst,
    }


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
    joint_schema: Optional[str] = None,
    confidence1: Optional[np.ndarray] = None,
    confidence2: Optional[np.ndarray] = None,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
    fps1: Optional[float] = None,
    fps2: Optional[float] = None,
) -> ToolResult:
    """Compute multi-dimensional similarity between two motion sequences.

    Args:
        seq1: (T1, J, 3) first motion sequence.
        seq2: (T2, J, 3) second motion sequence.
        confidence1/confidence2: Optional (T, J) confidence arrays used to
            filter low-quality aligned joints.

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
        confidence1 = _validate_confidence(confidence1, seq1.shape, "confidence1")
        confidence2 = _validate_confidence(confidence2, seq2.shape, "confidence2")
    except ValueError as exc:
        return ToolResult.fail(ErrorCode.INVALID_PARAM, str(exc))
    if not isinstance(confidence_threshold, (int, float)) or not (
        0.0 <= float(confidence_threshold) <= 1.0
    ):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "confidence_threshold must be between 0.0 and 1.0",
        )
    confidence_threshold = float(confidence_threshold)

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
        dtw_dist, alignment_path = fastdtw(flat1, flat2, dist=euclidean)
        max_len = max(len(flat1), len(flat2))
        dtw_normalized = dtw_dist / max_len

        vec1 = flat1.mean(axis=0)
        vec2 = flat2.mean(axis=0)
        cos_sim = float(
            np.dot(vec1, vec2)
            / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-8)
        )

        # Reuse the temporal alignment produced by FastDTW, then measure the
        # mean Euclidean distance between corresponding joints. The previous
        # implementation compared one Frobenius norm per frame, which could
        # hide large joint-level changes behind a similar global magnitude.
        aligned_joint_distances = np.array([
            np.linalg.norm(seq1_norm[left] - seq2_norm[right], axis=1)
            for left, right in alignment_path
        ])
        valid_mask = _alignment_valid_mask(
            alignment_path,
            seq1.shape[1],
            confidence1,
            confidence2,
            confidence_threshold,
        )
        valid_alignment_ratio = float(valid_mask.mean()) if valid_mask.size else 0.0
        if valid_mask.size and not valid_mask.any():
            return ToolResult.fail(
                ErrorCode.INVALID_PARAM,
                "No aligned joints passed the confidence quality gate.",
                meta={
                    "confidence_threshold": confidence_threshold,
                    "quality_gate": "no_valid_aligned_joints",
                },
            )
        shape_diff = _nanmean_or_zero(
            np.where(valid_mask, aligned_joint_distances, np.nan)
        )
        joint_diagnostics = _joint_distance_diagnostics(
            aligned_joint_distances,
            valid_mask,
            fps1,
            fps2,
        )
        _attach_worst_frame_times(joint_diagnostics, alignment_path, fps1, fps2)
        angle_report = _joint_angle_error_report(
            seq1,
            seq2,
            alignment_path,
            joint_schema,
            confidence1,
            confidence2,
            confidence_threshold,
            fps1,
            fps2,
        )
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

    quality_report = {
        "confidence_threshold": confidence_threshold,
        "min_valid_alignment_ratio": MIN_VALID_ALIGNMENT_RATIO,
        "valid_alignment_ratio": round(valid_alignment_ratio, 4),
        "accepted": valid_alignment_ratio >= MIN_VALID_ALIGNMENT_RATIO,
        "user_confidence": _confidence_basic_summary(
            confidence1,
            confidence_threshold,
        ),
        "reference_confidence": _confidence_basic_summary(
            confidence2,
            confidence_threshold,
        ),
    }

    return ToolResult.ok(
        data={
            "dtw_distance": round(dtw_normalized, 4),
            "cosine_similarity": round(cos_sim, 4),
            "shape_difference": round(shape_diff, 4),
            "joint_distance": joint_diagnostics,
            "joint_angle_errors": angle_report,
            "quality": quality_report,
            "labels": {
                "dtw": dtw_label,
                "cosine": cos_label,
                "shape": shape_label,
            },
            "overall_verdict": overall,
        },
        shape_difference_definition="dtw_aligned_mean_joint_distance",
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
    user_coordinate_space = str(
        user_sequence.metadata.get("coordinate_space") or ""
    )
    reference_coordinate_space = str(
        reference_sequence.metadata.get("coordinate_space") or ""
    )
    if (
        user_coordinate_space
        and reference_coordinate_space
        and user_coordinate_space != reference_coordinate_space
    ):
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "PoseSequence coordinate_space mismatch: "
            f"{user_coordinate_space} vs {reference_coordinate_space}",
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
        joint_schema=user_sequence.joint_schema,
        confidence1=user_sequence.confidence,
        confidence2=reference_sequence.confidence,
        fps1=user_sequence.fps,
        fps2=reference_sequence.fps,
    )
    if result.ok:
        result.meta.update(
            {
                "joint_schema": user_sequence.joint_schema,
                "pose_model": user_sequence.pose_model,
                "normalization": "hip_center_mean_scale",
                "coordinate_space": user_coordinate_space
                or reference_coordinate_space
                or "unknown",
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

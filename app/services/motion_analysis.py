"""Reusable orchestration for image and video motion analysis.

The service owns deterministic media-to-pose orchestration and structured
analysis summaries. HTTP upload limits, temporary-file lifecycle, user
authorization, persistence, and LLM explanation remain responsibilities of
their respective callers.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.tools import motion_tool, pose_estimator
from app.tools.pose_sequence import PoseSequence
from app.tools.types import ErrorCode, ToolResult


@dataclass(frozen=True)
class MotionImageAnalysis:
    """Structured result of one static image pose analysis."""

    sequence: PoseSequence
    confidence_summary: Optional[Dict[str, float]]
    warnings: List[str] = field(default_factory=list)
    execution_mode: str = "mediapipe_image"
    message: str = (
        "图片姿态已提取为 PoseSequence。当前返回静态姿态摘要；"
        "完整动作标准性判断需要视频序列或标准动作库对比。"
    )


@dataclass(frozen=True)
class MotionVideoAnalysis:
    """Structured result of one video pose extraction and optional comparison."""

    sequence: PoseSequence
    sampled_frames: int
    valid_frame_ratio: float
    confidence_summary: Optional[Dict[str, float]]
    reference: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    execution_mode: str = "mediapipe_video"
    message: str = "视频已转换为多帧 PoseSequence。"


def _confidence_summary(sequence: PoseSequence) -> Optional[Dict[str, float]]:
    if sequence.confidence is None:
        return None
    confidence = sequence.confidence.astype(float)
    return {
        "mean": round(float(confidence.mean()), 4),
        "min": round(float(confidence.min()), 4),
        "max": round(float(confidence.max()), 4),
    }


def _forward_failure(result: ToolResult, *, stage: str) -> ToolResult:
    """Preserve the underlying error while identifying the failed service stage."""
    meta = dict(result.meta)
    meta["stage"] = stage
    return ToolResult.fail(
        result.error_code or ErrorCode.INTERNAL_ERROR,
        result.error_message or "Motion analysis failed",
        data=result.data,
        **meta,
    )


def analyze_motion_image_bytes(content: bytes, *, filename: str) -> ToolResult:
    """Decode an uploaded image and produce a bounded static-pose summary.

    The caller must enforce upload-size limits before invoking this function.
    The function does not persist the image and does not call an LLM.
    """
    if not isinstance(filename, str) or not filename.strip():
        return ToolResult.fail(ErrorCode.INVALID_PARAM, "Image filename is required")
    if not isinstance(content, bytes):
        return ToolResult.fail(ErrorCode.INVALID_PARAM, "Image content must be bytes")

    image_result = pose_estimator.decode_image_bytes_to_rgb(content, filename=filename)
    if not image_result.ok:
        return _forward_failure(image_result, stage="image_decode")

    pose_result = pose_estimator.estimate_pose_from_image(
        image_result.data,
        source_name=filename,
    )
    if not pose_result.ok:
        return _forward_failure(pose_result, stage="image_pose_estimation")

    sequence = pose_result.data
    confidence_summary = _confidence_summary(sequence)
    warnings = ["单张图片只能分析静态姿态，不能判断动作节奏、轨迹或发力顺序。"]
    if confidence_summary is not None and confidence_summary["mean"] < 0.5:
        warnings.append("关键点整体置信度较低，建议更换清晰、无遮挡的图片。")

    return ToolResult.ok(
        data=MotionImageAnalysis(
            sequence=sequence,
            confidence_summary=confidence_summary,
            warnings=warnings,
        ),
        stage="complete",
    )


def analyze_motion_video_path(
    video_path: str,
    *,
    filename: str,
    motion_library_dir: str,
    reference_name: Optional[str] = None,
) -> ToolResult:
    """Extract a video pose sequence and optionally compare a named reference.

    The caller owns the video file lifecycle. Only references discovered under
    ``motion_library_dir`` are accepted; arbitrary reference paths are never
    read from user input.
    """
    if not isinstance(filename, str) or not filename.strip():
        return ToolResult.fail(ErrorCode.INVALID_PARAM, "Video filename is required")

    pose_result = pose_estimator.estimate_pose_from_video_path(
        video_path,
        source_name=filename,
    )
    if not pose_result.ok:
        return _forward_failure(pose_result, stage="video_pose_estimation")

    sequence = pose_result.data
    metadata = sequence.metadata
    confidence_summary = _confidence_summary(sequence)
    valid_frame_ratio = float(metadata.get("valid_frame_ratio", 0.0))
    warnings: List[str] = []
    if valid_frame_ratio < 0.8:
        warnings.append("有效姿态帧比例较低，建议使用单人、无遮挡、固定机位视频。")

    normalized_reference = reference_name.strip() if reference_name else ""
    if normalized_reference and len(normalized_reference) > 64:
        return ToolResult.fail(
            ErrorCode.INVALID_PARAM,
            "reference_name is too long",
            stage="reference_validation",
        )

    reference: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    execution_mode = "mediapipe_video"
    message = "视频已转换为多帧 PoseSequence。"

    if normalized_reference:
        library_result = motion_tool.list_motion_library(motion_library_dir)
        library = library_result.data if library_result.ok else {}
        reference_path = library.get(normalized_reference)
        if reference_path is None:
            return ToolResult.fail(
                ErrorCode.DATA_NOT_FOUND,
                f"Reference motion not found: {normalized_reference}",
                stage="reference_lookup",
            )

        reference_result = motion_tool.load_npz_pose_sequence(reference_path)
        if not reference_result.ok:
            return _forward_failure(reference_result, stage="reference_load")

        similarity_result = motion_tool.compute_pose_sequence_similarity(
            sequence,
            reference_result.data,
        )
        if not similarity_result.ok:
            return _forward_failure(similarity_result, stage="motion_comparison")

        reference = normalized_reference
        metrics = similarity_result.data
        execution_mode = "mediapipe_video_similarity"
        message = "视频已转换为 PoseSequence，并完成与标准动作的相似度分析。"
        warnings.append(
            "相似度仅表示与所选标准样本的统计接近程度，不等同于专业教练的动作质量诊断。"
        )
        quality = metrics.get("quality") if isinstance(metrics, dict) else None
        if isinstance(quality, dict) and quality.get("accepted") is False:
            warnings.append(
                "关键点有效对齐比例低于质量门控阈值，本次相似度仅作低置信参考，"
                "建议重新拍摄后再判断。"
            )
    else:
        warnings.append("未选择标准动作，本次仅提取多帧 PoseSequence，不执行相似度评分。")

    return ToolResult.ok(
        data=MotionVideoAnalysis(
            sequence=sequence,
            sampled_frames=int(metadata.get("sampled_frames", sequence.frames)),
            valid_frame_ratio=round(valid_frame_ratio, 4),
            confidence_summary=confidence_summary,
            reference=reference,
            metrics=metrics,
            warnings=warnings,
            execution_mode=execution_mode,
            message=message,
        ),
        stage="complete",
    )

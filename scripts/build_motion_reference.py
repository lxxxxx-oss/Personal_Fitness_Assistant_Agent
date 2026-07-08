"""Build a schema-safe standard PoseSequence from a reference video."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import config
from app.tools.pose_estimator import estimate_pose_from_video_path
from app.tools.pose_sequence import pose_sequence_to_npz_payload

REFERENCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def build_reference(
    video_path: Path,
    name: str,
    library_dir: Path,
    *,
    overwrite: bool = False,
) -> dict:
    """Convert one user-selected standard video into a library PoseSequence."""
    if not REFERENCE_NAME_PATTERN.fullmatch(name):
        raise ValueError("name must match [A-Za-z0-9_-]{1,64}")
    if not video_path.is_file():
        raise FileNotFoundError(f"Reference video not found: {video_path}")

    output_path = library_dir / f"{name}.npz"
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Reference already exists: {output_path}; pass --overwrite to replace it"
        )

    result = estimate_pose_from_video_path(
        str(video_path),
        source_name=video_path.name,
    )
    if not result.ok:
        raise RuntimeError(result.error_message or "Reference pose extraction failed")

    sequence = result.data
    sequence.metadata.update(
        {
            "reference_name": name,
            "source_video": video_path.name,
            "reference_builder": "scripts/build_motion_reference.py",
        }
    )
    library_dir.mkdir(parents=True, exist_ok=True)
    payload = pose_sequence_to_npz_payload(sequence)
    with output_path.open("wb") as output_file:
        np.savez_compressed(output_file, **payload)
    return {"path": str(output_path), **sequence.summary()}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a MediaPipe PoseSequence reference from a standard video."
    )
    parser.add_argument("video", type=Path, help="Path to the standard motion video")
    parser.add_argument("--name", required=True, help="Reference name: letters/numbers/_/-")
    parser.add_argument(
        "--library-dir",
        type=Path,
        default=Path(config.motion_library_dir),
        help="Motion library directory",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        summary = build_reference(
            args.video,
            args.name,
            args.library_dir,
            overwrite=args.overwrite,
        )
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError) as exc:
        parser.error(str(exc))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

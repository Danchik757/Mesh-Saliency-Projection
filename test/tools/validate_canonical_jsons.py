#!/usr/bin/env python3
"""Validate repository-local canonical camera JSONs.

The checks here intentionally validate the fields used by the projection code:
camera matrices, model scale/location, video timing, and per-frame rotations.
They do not compare against external datasets, so the script works on local
machines and servers immediately after `git pull`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_SETS = {
    "mamba_non_jsons": {
        "prefix": "MeshMamba_non_texture_",
        "count": 105,
        "frames": 510,
        "fps": 30,
    },
    "mamba_rgb_jsons": {
        "prefix": "MeshMamba_rgb_texture_",
        "count": 105,
        "frames": 510,
        "fps": 30,
    },
    "3dva_jsons": {
        "prefix": "3DVA_",
        "count": 32,
        "frames": 510,
        "fps": 30,
    },
    "sal3d_jsons": {
        "prefix": "Sal3D_",
        "count": 57,
        "frames": 720,
        "fps": 30,
    },
}

REQUIRED_TOP = {
    "animation",
    "camera_static",
    "file_version",
    "frames",
    "generated_at",
    "model_name",
    "model_static",
    "video_info",
}
REQUIRED_CAMERA = {
    "location",
    "rotation_euler_radians",
    "rotation_euler_degrees",
    "fov_radians",
    "fov_degrees",
    "lens_mm",
    "sensor_width_mm",
    "sensor_height_mm",
    "clip_start",
    "clip_end",
    "projection_matrix",
    "view_matrix",
}
REQUIRED_MODEL = {"location", "scale", "bbox_max_dimensions"}
REQUIRED_VIDEO = {
    "fps",
    "duration_seconds",
    "total_frames",
    "resolution_width",
    "resolution_height",
    "aspect_ratio",
}
REQUIRED_ANIMATION = {
    "start_angle_radians",
    "start_angle_degrees",
    "rotation_speed_deg_per_sec",
    "rotation_speed_rad_per_sec",
    "rotation_axis",
    "rotation_direction",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json-root",
        type=Path,
        default=REPO_ROOT / "jsons",
        help="Root containing 3dva_jsons, mamba_*_jsons, and sal3d_jsons.",
    )
    return parser.parse_args()


def is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def flatten_numbers(value: Any) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        out: list[float] = []
        for item in value:
            out.extend(flatten_numbers(item))
        return out
    return []


def is_finite_sequence(value: Any, length: int | None = None) -> bool:
    numbers = flatten_numbers(value)
    if length is not None and len(numbers) != length:
        return False
    return bool(numbers) and all(math.isfinite(x) for x in numbers)


def normalized_name(value: Any) -> str:
    return str(value).lower().replace("-", "_").replace(" ", "_")


def validate_required_keys(path: Path, data: dict[str, Any], errors: list[str]) -> None:
    required_groups = [
        (REQUIRED_TOP, "top", data),
        (REQUIRED_CAMERA, "camera_static", data.get("camera_static", {})),
        (REQUIRED_MODEL, "model_static", data.get("model_static", {})),
        (REQUIRED_VIDEO, "video_info", data.get("video_info", {})),
        (REQUIRED_ANIMATION, "animation", data.get("animation", {})),
    ]
    for required, label, container in required_groups:
        if not isinstance(container, dict):
            errors.append(f"{path}: {label} is not an object")
            continue
        missing = sorted(required - set(container))
        if missing:
            errors.append(f"{path}: missing {label} keys {missing}")


def validate_file(
    path: Path,
    prefix: str,
    expected_frames: int,
    expected_fps: int,
    errors: list[str],
    warnings: list[str],
) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - diagnostic script
        errors.append(f"{path}: cannot parse JSON: {exc}")
        return

    validate_required_keys(path, data, errors)

    camera = data.get("camera_static", {})
    model = data.get("model_static", {})
    video = data.get("video_info", {})
    animation = data.get("animation", {})
    frames = data.get("frames", [])

    if not path.name.startswith(prefix):
        errors.append(f"{path}: filename prefix mismatch, expected {prefix}")

    filename_model = path.stem.removeprefix(prefix)
    if normalized_name(data.get("model_name", "")) != normalized_name(filename_model):
        warnings.append(
            f"{path}: model_name={data.get('model_name')!r} "
            f"differs from filename model {filename_model!r}"
        )

    if len(frames) != video.get("total_frames"):
        errors.append(f"{path}: frames {len(frames)} != total_frames {video.get('total_frames')}")
    if len(frames) != expected_frames:
        errors.append(f"{path}: frames {len(frames)} != expected {expected_frames}")
    if int(video.get("fps", -1)) != expected_fps:
        errors.append(f"{path}: fps {video.get('fps')} != expected {expected_fps}")
    if int(video.get("resolution_width", 0)) != 1920 or int(video.get("resolution_height", 0)) != 1080:
        errors.append(f"{path}: resolution must be 1920x1080")
    if abs(float(video.get("aspect_ratio", 0.0)) - 16.0 / 9.0) > 1e-6:
        errors.append(f"{path}: aspect_ratio {video.get('aspect_ratio')} != 16/9")

    if not is_finite_sequence(camera.get("projection_matrix"), 16):
        errors.append(f"{path}: bad camera_static.projection_matrix")
    if not is_finite_sequence(camera.get("view_matrix"), 16):
        errors.append(f"{path}: bad camera_static.view_matrix")
    for key in ("location", "rotation_euler_radians", "rotation_euler_degrees"):
        if not is_finite_sequence(camera.get(key), 3):
            errors.append(f"{path}: bad camera_static.{key}")
    if not (
        is_finite_number(camera.get("clip_start"))
        and is_finite_number(camera.get("clip_end"))
        and float(camera["clip_start"]) > 0
        and float(camera["clip_end"]) > float(camera["clip_start"])
    ):
        errors.append(f"{path}: bad camera clip range")
    if not (is_finite_number(camera.get("fov_degrees")) and 0 < float(camera["fov_degrees"]) < 180):
        errors.append(f"{path}: bad camera_static.fov_degrees")

    if not is_finite_sequence(model.get("location"), 3):
        errors.append(f"{path}: bad model_static.location")
    if not is_finite_sequence(model.get("scale"), 3) or min(flatten_numbers(model.get("scale"))) <= 0:
        errors.append(f"{path}: bad model_static.scale")
    bbox = model.get("bbox_max_dimensions", {})
    for key in ("width", "depth", "height"):
        if key not in bbox or not is_finite_number(bbox[key]) or float(bbox[key]) <= 0:
            errors.append(f"{path}: bad model_static.bbox_max_dimensions.{key}")

    if animation.get("rotation_axis") != "Z":
        errors.append(f"{path}: rotation_axis must be Z")
    if animation.get("rotation_direction") != "counter_clockwise":
        errors.append(f"{path}: rotation_direction must be counter_clockwise")

    if not frames:
        errors.append(f"{path}: frames list is empty")
        return

    if frames[0].get("frame") != 1:
        errors.append(f"{path}: first frame index must be 1")
    if frames[-1].get("frame") != len(frames):
        errors.append(f"{path}: last frame index must equal frame count")

    previous_timestamp = -1.0
    previous_rotation = -1.0e18
    max_rad_deg_delta = 0.0
    for index, frame in enumerate(frames, start=1):
        timestamp = float(frame.get("timestamp", math.nan))
        rotation_deg = float(frame.get("rotation_z_degrees", math.nan))
        rotation_rad = float(frame.get("rotation_z_radians", math.nan))
        if not (math.isfinite(timestamp) and math.isfinite(rotation_deg) and math.isfinite(rotation_rad)):
            errors.append(f"{path}: non-finite data at frame {index}")
        if int(frame.get("frame", -1)) != index:
            errors.append(f"{path}: frame index mismatch at {index}: {frame.get('frame')}")
        if timestamp < previous_timestamp:
            errors.append(f"{path}: timestamp decreases at frame {index}")
        if rotation_deg < previous_rotation - 1e-6:
            errors.append(f"{path}: rotation decreases at frame {index}")
        max_rad_deg_delta = max(max_rad_deg_delta, abs(math.degrees(rotation_rad) - rotation_deg))
        previous_timestamp = timestamp
        previous_rotation = rotation_deg

    if abs(float(frames[0].get("timestamp", 999.0))) > 1e-9:
        errors.append(f"{path}: first timestamp must be zero")
    expected_last_timestamp = (len(frames) - 1) / expected_fps
    if abs(float(frames[-1].get("timestamp")) - expected_last_timestamp) > 1e-6:
        errors.append(f"{path}: last timestamp mismatch")
    if max_rad_deg_delta > 1e-4:
        errors.append(f"{path}: rotation radians/degrees mismatch max {max_rad_deg_delta}")


def main() -> int:
    args = parse_args()
    root = args.json_root
    errors: list[str] = []
    warnings: list[str] = []
    total = 0

    for dirname, spec in EXPECTED_SETS.items():
        directory = root / dirname
        files = sorted(directory.glob("*.json"))
        total += len(files)
        if len(files) != spec["count"]:
            errors.append(f"{directory}: expected {spec['count']} JSON files, found {len(files)}")
        for path in files:
            validate_file(
                path=path,
                prefix=str(spec["prefix"]),
                expected_frames=int(spec["frames"]),
                expected_fps=int(spec["fps"]),
                errors=errors,
                warnings=warnings,
            )

    print(f"VALIDATED_JSON_FILES {total}")
    print(f"ERRORS {len(errors)}")
    print(f"WARNINGS {len(warnings)}")
    for dirname in sorted(EXPECTED_SETS):
        print(f"{dirname}.count {len(list((root / dirname).glob('*.json')))}")

    if warnings:
        print("\nWARNINGS_SAMPLE")
        for warning in warnings[:50]:
            print(warning)

    if errors:
        print("\nERRORS")
        for error in errors:
            print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

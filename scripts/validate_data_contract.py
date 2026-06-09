#!/usr/bin/env python3
"""Validate repository-local placement, original gaze CSV, and processed gaze JSON."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


TRACKS = {
    "3DVA": {
        "placement_dir": "3dva_jsons",
        "placement_prefix": "3DVA_",
        "csv_dir": "3DVA",
        "processed_prefix": "3DVA_",
        "expected": 32,
    },
    "MeshMamba_non_texture": {
        "placement_dir": "mamba_non_jsons",
        "placement_prefix": "MeshMamba_non_texture_",
        "csv_dir": "MeshMamba_non_texture",
        "processed_prefix": "MeshMamba_non_texture_",
        "expected": 105,
    },
    "MeshMamba_rgb_texture": {
        "placement_dir": "mamba_rgb_jsons",
        "placement_prefix": "MeshMamba_rgb_texture_",
        "csv_dir": "MeshMamba_rgb_texture",
        "processed_prefix": "MeshMamba_rgb_texture_",
        "expected": 105,
    },
    "SAL3D": {
        "placement_dir": "sal3d_jsons",
        "placement_prefix": "Sal3D_",
        "csv_dir": "SAL3D",
        "processed_prefix": "SAL3D_",
        "expected": 57,
    },
}

REQUIRED_CSV_COLUMNS = {
    "participation_id",
    "video_id",
    "data_gazes",
}

KNOWN_BLOCKERS = {
    "3DVA": {"invalid_processed": {"jessi"}},
    "SAL3D": {"missing_csv": {"gorgoile"}, "missing_processed": {"gorgoile"}},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--allow-known-blockers", action="store_true")
    return parser.parse_args()


def strip_prefix(name: str, prefix: str) -> str:
    if not name.lower().startswith(prefix.lower()):
        raise ValueError(f"{name!r} does not start with {prefix!r}")
    return name[len(prefix) :]


def unwrapped_rotation_degrees(frames: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for frame in frames:
        if "rotation_z_degrees" in frame:
            angle = float(frame["rotation_z_degrees"])
        else:
            angle = math.degrees(float(frame["rotation_z_radians"]))
        if values:
            while angle - values[-1] > 180.0:
                angle -= 360.0
            while angle - values[-1] < -180.0:
                angle += 360.0
        values.append(angle)
    return values


def inspect_csv(path: Path) -> dict[str, Any]:
    rows = 0
    gaze_points = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_CSV_COLUMNS - columns)
        for row in reader:
            rows += 1
            gaze = ast.literal_eval(row["data_gazes"])
            if not isinstance(gaze, dict) or not {"t", "x", "y"} <= set(gaze):
                raise ValueError("data_gazes must be a dict containing t/x/y arrays")
            lengths = {len(gaze[key]) for key in ("t", "x", "y")}
            if len(lengths) != 1:
                raise ValueError(f"data_gazes t/x/y length mismatch: {sorted(lengths)}")
            gaze_points += lengths.pop()
    return {"rows": rows, "gaze_points": gaze_points, "missing_columns": missing_columns}


def inspect_processed(path: Path, expected_frames: int, width: int, height: int) -> dict[str, Any]:
    frames = json.loads(path.read_text())
    if not isinstance(frames, list):
        raise ValueError("top level must be a list of frames")
    point_count = 0
    empty_frames = 0
    out_of_bounds = 0
    for frame in frames:
        if not isinstance(frame, list):
            raise ValueError("each frame must be a list")
        empty_frames += int(not frame)
        for point in frame:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in point)
            ):
                raise ValueError(f"invalid point: {point!r}")
            x_px, y_px = point
            out_of_bounds += int(x_px < 0 or x_px >= width or y_px < 0 or y_px >= height)
            point_count += 1
    return {
        "frames": len(frames),
        "expected_frames": expected_frames,
        "point_count": point_count,
        "empty_frames": empty_frames,
        "out_of_bounds": out_of_bounds,
    }


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    placement_root = repo / "jsons" / "object_placement"
    csv_root = repo / "participant_data" / "collected_gaze_csv_by_model"
    processed_root = repo / "participant_data" / "processed_fixations_offset_2000"
    result: dict[str, Any] = {"repo_root": str(repo), "tracks": {}, "errors": [], "known_blockers": []}

    for track, config in TRACKS.items():
        placements: dict[str, Path] = {}
        placement_meta: dict[str, dict[str, Any]] = {}
        for path in sorted((placement_root / config["placement_dir"]).glob("*.json")):
            model = strip_prefix(path.stem, config["placement_prefix"])
            meta = json.loads(path.read_text())
            placements[model.lower()] = path
            placement_meta[model.lower()] = meta

        csvs = {path.stem.lower(): path for path in sorted((csv_root / config["csv_dir"]).glob("*.csv"))}
        processed = {}
        for path in sorted(processed_root.glob(f"{config['processed_prefix']}*/fixations.json")):
            model = strip_prefix(path.parent.name, config["processed_prefix"])
            processed[model.lower()] = path

        missing_csv = sorted(set(placements) - set(csvs))
        missing_processed = sorted(set(placements) - set(processed))
        extra_csv = sorted(set(csvs) - set(placements))
        extra_processed = sorted(set(processed) - set(placements))
        track_result: dict[str, Any] = {
            "expected_models": config["expected"],
            "placement_count": len(placements),
            "original_csv_count": len(csvs),
            "processed_json_count": len(processed),
            "missing_original_csv": missing_csv,
            "missing_processed_json": missing_processed,
            "extra_original_csv": extra_csv,
            "extra_processed_json": extra_processed,
            "timing_groups": {},
            "invalid_models": {},
        }

        timing_groups: Counter[str] = Counter()
        invalid_placement: dict[str, list[str]] = {}
        invalid_csv: dict[str, list[str]] = {}
        invalid_processed: dict[str, list[str]] = {}
        for model, meta in placement_meta.items():
            try:
                video = meta["video_info"]
                frames = meta["frames"]
                fps = float(video["fps"])
                duration = float(video["duration_seconds"])
                total_frames = int(video["total_frames"])
                rotation_speed = float(meta["animation"]["rotation_speed_deg_per_sec"])
                full_turn_seconds = abs(360.0 / rotation_speed)
                crop_start_frames = round(1.8 * fps)
                crop_end_frames = round(0.2 * fps)
                end_frame_exclusive = total_frames - crop_end_frames
                usable_frames = end_frame_exclusive - crop_start_frames
                usable_seconds = usable_frames / fps
                if len(frames) != total_frames:
                    raise ValueError(f"placement frames {len(frames)} != total_frames {total_frames}")
                timestamps = [float(frame["timestamp"]) for frame in frames]
                if any(b < a for a, b in zip(timestamps, timestamps[1:])):
                    raise ValueError("placement timestamps are not monotonic")
                expected_last = (total_frames - 1) / fps
                if not math.isclose(timestamps[-1], expected_last, abs_tol=1e-6):
                    raise ValueError(
                        f"last timestamp {timestamps[-1]} != expected {expected_last}"
                    )
                unwrapped = unwrapped_rotation_degrees(frames)
                # Exported placement rotations sample the full declared video duration
                # inclusively across total_frames entries. Therefore validate the
                # endpoint against duration_seconds, not against the last frame timestamp.
                observed_speed = (unwrapped[-1] - unwrapped[0]) / duration
                if not math.isclose(observed_speed, rotation_speed, rel_tol=1e-5, abs_tol=1e-5):
                    raise ValueError(
                        f"observed rotation speed {observed_speed} != declared {rotation_speed}"
                    )
                full_turn_degrees = abs(rotation_speed) * usable_seconds
                if not math.isclose(usable_seconds, full_turn_seconds, abs_tol=1.0 / fps + 1e-6):
                    raise ValueError(
                        f"cropped duration {usable_seconds} is not one turn {full_turn_seconds}"
                    )
                if not math.isclose(full_turn_degrees, 360.0, abs_tol=abs(rotation_speed) / fps + 1e-6):
                    raise ValueError(f"cropped interval covers {full_turn_degrees} degrees")
                timing_key = json.dumps(
                    {
                        "fps": fps,
                        "video_seconds": duration,
                        "total_frames": total_frames,
                        "rotation_speed_deg_per_sec": rotation_speed,
                        "observed_speed_deg_per_sec": round(observed_speed, 6),
                        "full_turn_seconds": full_turn_seconds,
                        "placement_start_frame_zero_based": crop_start_frames,
                        "placement_end_frame_exclusive_zero_based": end_frame_exclusive,
                        "usable_frames": usable_frames,
                        "usable_seconds": usable_seconds,
                    },
                    sort_keys=True,
                )
                timing_groups[timing_key] += 1
            except Exception as exc:  # noqa: BLE001 - validator must report all files
                invalid_placement.setdefault(model, []).append(str(exc))

        track_result["timing_groups"] = {
            key: count for key, count in sorted(timing_groups.items(), key=lambda item: item[0])
        }

        for model, path in csvs.items():
            try:
                info = inspect_csv(path)
                if info["missing_columns"]:
                    invalid_csv.setdefault(model, []).append(
                        f"CSV missing columns: {info['missing_columns']}"
                    )
            except Exception as exc:  # noqa: BLE001 - validator must report all files
                invalid_csv.setdefault(model, []).append(str(exc))

        for model, path in processed.items():
            meta = placement_meta.get(model)
            if meta is None:
                continue
            video = meta["video_info"]
            try:
                info = inspect_processed(
                    path,
                    int(video["total_frames"]),
                    int(video["resolution_width"]),
                    int(video["resolution_height"]),
                )
                if info["frames"] != info["expected_frames"]:
                    invalid_processed.setdefault(model, []).append(
                        f"processed frames {info['frames']} != placement frames {info['expected_frames']}"
                    )
                if info["empty_frames"]:
                    invalid_processed.setdefault(model, []).append(
                        f"processed JSON has {info['empty_frames']} empty frames"
                    )
                if info["out_of_bounds"]:
                    invalid_processed.setdefault(model, []).append(
                        f"processed JSON has {info['out_of_bounds']} out-of-bounds points"
                    )
            except Exception as exc:  # noqa: BLE001 - validator must report all files
                invalid_processed.setdefault(model, []).append(str(exc))

        track_result["invalid_models"] = {
            "placement": invalid_placement,
            "original_csv": invalid_csv,
            "processed_json": invalid_processed,
        }

        known = KNOWN_BLOCKERS.get(track, {})
        for category, models in (
            ("missing_csv", missing_csv),
            ("missing_processed", missing_processed),
            ("invalid_processed", invalid_processed),
        ):
            expected_known = known.get(category, set())
            for model in models:
                message = f"{track}:{category}:{model}"
                if model in expected_known:
                    result["known_blockers"].append(message)
                else:
                    result["errors"].append(message)

        for category, invalid in (
            ("invalid_placement", invalid_placement),
            ("invalid_csv", invalid_csv),
        ):
            result["errors"].extend(f"{track}:{category}:{model}" for model in invalid)

        if len(placements) != config["expected"]:
            result["errors"].append(f"{track}: placement count {len(placements)} != {config['expected']}")
        if extra_csv or extra_processed:
            result["errors"].append(f"{track}: unexpected extra participant data")
        result["tracks"][track] = track_result

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    if result["errors"]:
        return 1
    if result["known_blockers"] and not args.allow_known_blockers:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

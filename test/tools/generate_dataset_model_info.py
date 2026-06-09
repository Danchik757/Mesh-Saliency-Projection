#!/usr/bin/env python3
"""Generate platform-independent dataset/model indexes from placement JSONs."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CROP_START_SECONDS = 1.8
CROP_END_SECONDS = 0.2


@dataclass(frozen=True)
class DatasetSpec:
    dataset: str
    track: str
    placement_dir: str
    placement_prefix: str
    participant_csv_dir: str
    processed_prefix: str
    mesh_release_template: str
    gt_release_templates: tuple[str, ...]
    gt_type: str
    output_file: str
    notes: tuple[str, ...] = ()


SPECS = [
    DatasetSpec(
        dataset="3DVA",
        track="3dva",
        placement_dir="3dva_jsons",
        placement_prefix="3DVA_",
        participant_csv_dir="3DVA",
        processed_prefix="3DVA_",
        mesh_release_template="datasets/3DVA/3DModels-Simplif-up/{model}.obj",
        gt_release_templates=(
            "datasets/3DVA/FixationMaps/{model}_300norm.txt",
            "datasets/3DVA/FixationMaps/{model}_413norm.txt",
            "datasets/3DVA/FixationMaps/{model}_599norm.txt",
            "datasets/3DVA/CombinedGT/{model}_combined_gt.txt",
        ),
        gt_type="per_vertex_static_views_plus_combined",
        output_file="3dva_models.json",
        notes=(
            "3DVA GT views 300/413/599 are static-view fixation maps, not dynamic-video GT.",
            "Use the corrected 3DModels-Simplif-up OBJ archive.",
        ),
    ),
    DatasetSpec(
        dataset="MeshMamba",
        track="non_texture",
        placement_dir="mamba_non_jsons",
        placement_prefix="MeshMamba_non_texture_",
        participant_csv_dir="MeshMamba_non_texture",
        processed_prefix="MeshMamba_non_texture_",
        mesh_release_template="datasets/MeshMamba/MeshFile/non_texture/{model}/{model}.obj",
        gt_release_templates=("datasets/MeshMamba/SaliencyMap/non_texture/{model}.csv",),
        gt_type="per_face",
        output_file="meshmamba_non_texture_models.json",
        notes=("Mesh and GT names may require deterministic case-insensitive alias resolution.",),
    ),
    DatasetSpec(
        dataset="MeshMamba",
        track="rgb_texture",
        placement_dir="mamba_rgb_jsons",
        placement_prefix="MeshMamba_rgb_texture_",
        participant_csv_dir="MeshMamba_rgb_texture",
        processed_prefix="MeshMamba_rgb_texture_",
        mesh_release_template="datasets/MeshMamba/MeshFile/rgb_texture/{model}/{model}.obj",
        gt_release_templates=("datasets/MeshMamba/SaliencyMap/rgb_texture/{model}.csv",),
        gt_type="per_face",
        output_file="meshmamba_rgb_texture_models.json",
        notes=("Mesh and GT names may require deterministic case-insensitive alias resolution.",),
    ),
    DatasetSpec(
        dataset="SAL3D",
        track="sal3d",
        placement_dir="sal3d_jsons",
        placement_prefix="Sal3D_",
        participant_csv_dir="SAL3D",
        processed_prefix="SAL3D_",
        mesh_release_template="datasets/SAL3D/Meshes/{model}.obj",
        gt_release_templates=("datasets/SAL3D/Gaze/{model}.txt",),
        gt_type="per_vertex_subset",
        output_file="sal3d_models.json",
        notes=(
            "SAL3D gorgoile currently has no original CSV or processed fixation JSON.",
            "Smooth_Gaze is auxiliary GT data, not participant gaze JSON.",
        ),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--placement-root",
        type=Path,
        default=REPO_ROOT / "jsons" / "object_placement",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "jsons" / "dataset_model_info",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_camera(camera: dict[str, Any]) -> dict[str, Any]:
    return {
        "location": camera.get("location"),
        "rotation_euler_degrees": camera.get("rotation_euler_degrees"),
        "fov_degrees": camera.get("fov_degrees"),
        "lens_mm": camera.get("lens_mm"),
        "sensor_width_mm": camera.get("sensor_width_mm"),
        "sensor_height_mm": camera.get("sensor_height_mm"),
        "clip_start": camera.get("clip_start"),
        "clip_end": camera.get("clip_end"),
        "has_view_matrix": "view_matrix" in camera,
        "has_projection_matrix": "projection_matrix" in camera,
    }


def model_from_json_name(path: Path, prefix: str) -> str:
    if not path.stem.lower().startswith(prefix.lower()):
        raise ValueError(f"{path.name} does not start with {prefix}")
    return path.stem[len(prefix) :]


def participant_paths(spec: DatasetSpec, model: str) -> dict[str, Any]:
    old_csv_rel = f"{spec.participant_csv_dir}/{model}.csv"
    processed_rel = f"{spec.processed_prefix}{model}/fixations.json"
    return {
        "default_format": "processed_fixations_json",
        "automatic_fallback_allowed": False,
        "processed_fixations_json": {
            "repository_staging_path": (
                f"participant_data/processed_fixations_offset_2000/{processed_rel}"
            ),
            "release_path": (
                f"participant_fixations_processed_offset_2000/{processed_rel}"
            ),
            "timing": "implicit_frame_index",
            "participant_ids_available": False,
        },
        "original_csv_compatibility": {
            "repository_staging_path": (
                f"participant_data/collected_gaze_csv_by_model/{old_csv_rel}"
            ),
            "release_path": f"participant_gaze_csv_original/{old_csv_rel}",
            "timing": "explicit_t_seconds",
            "participant_ids_available": True,
        },
    }


def timing_contract(data: dict[str, Any]) -> dict[str, Any]:
    video = data["video_info"]
    animation = data["animation"]
    fps = float(video["fps"])
    total_frames = int(video["total_frames"])
    rotation_speed = abs(float(animation["rotation_speed_deg_per_sec"]))
    start_frame = round(CROP_START_SECONDS * fps)
    end_frame_exclusive = total_frames - round(CROP_END_SECONDS * fps)
    return {
        "crop_start_seconds": CROP_START_SECONDS,
        "crop_end_seconds": CROP_END_SECONDS,
        "placement_start_frame_zero_based": start_frame,
        "placement_end_frame_exclusive_zero_based": end_frame_exclusive,
        "usable_frames": end_frame_exclusive - start_frame,
        "full_turn_seconds_from_rotation_speed": 360.0 / rotation_speed,
        "pairing_rule": "processed_gaze[k] -> placement[start_frame + k]",
    }


def build_dataset_index(spec: DatasetSpec, placement_root: Path) -> dict[str, Any]:
    json_root = placement_root / spec.placement_dir
    models = []
    for json_path in sorted(json_root.glob("*.json"), key=lambda path: path.name.lower()):
        model = model_from_json_name(json_path, spec.placement_prefix)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        models.append(
            {
                "model": model,
                "model_name_in_json": data.get("model_name"),
                "placement_json": {
                    "repository_path": str(json_path.relative_to(REPO_ROOT)),
                    "release_path": (
                        f"object_placement_json_canonical/{spec.placement_dir}/{json_path.name}"
                    ),
                    "sha256": sha256(json_path),
                },
                "participant_data": participant_paths(spec, model),
                "mesh": {
                    "release_path": spec.mesh_release_template.format(model=model),
                    "resolution_policy": (
                        "exact"
                        if spec.dataset in {"3DVA", "SAL3D"}
                        else "deterministic_case_insensitive_alias"
                    ),
                },
                "ground_truth": {
                    "type": spec.gt_type,
                    "release_paths": [
                        template.format(model=model) for template in spec.gt_release_templates
                    ],
                },
                "render_and_projection": {
                    "camera_static": compact_camera(data.get("camera_static", {})),
                    "model_static": data.get("model_static", {}),
                    "animation": data.get("animation", {}),
                    "video_info": data.get("video_info", {}),
                    "timing_contract": timing_contract(data),
                    "frame_count": len(data.get("frames", [])),
                    "first_frame": data.get("frames", [None])[0],
                    "last_frame": data.get("frames", [None])[-1],
                },
            }
        )

    return {
        "dataset": spec.dataset,
        "track": spec.track,
        "purpose": (
            "platform-independent model index linking canonical placement, separate "
            "participant inputs, release meshes, and GT"
        ),
        "object_placement_json_root": str(
            (placement_root / spec.placement_dir).relative_to(REPO_ROOT)
        ),
        "model_count": len(models),
        "participant_data_default": "processed_fixations_json",
        "participant_data_compatibility": "original_csv_explicit_only",
        "notes": list(spec.notes),
        "models": models,
    }


def main() -> int:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    summary = {
        "purpose": "platform-independent summary of repository and release data organization",
        "object_placement_root": str(args.placement_root.relative_to(REPO_ROOT)),
        "dataset_model_info_root": str(args.output_root.relative_to(REPO_ROOT)),
        "participant_data_contract": {
            "default": "processed_fixations_json",
            "compatibility_only": "original_csv",
            "automatic_fallback_allowed": False,
            "repository_staging_roots": {
                "processed_fixations_json": "participant_data/processed_fixations_offset_2000",
                "original_csv": "participant_data/collected_gaze_csv_by_model",
            },
            "release_roots": {
                "processed_fixations_json": "participant_fixations_processed_offset_2000",
                "original_csv": "participant_gaze_csv_original",
            },
        },
        "timing_contract": {
            "crop_start_seconds": CROP_START_SECONDS,
            "crop_end_seconds": CROP_END_SECONDS,
            "derive_full_turn_from_placement_json": True,
        },
        "datasets": [],
    }

    for spec in SPECS:
        index = build_dataset_index(spec, args.placement_root)
        out_path = args.output_root / spec.output_file
        out_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        summary["datasets"].append(
            {
                "dataset": spec.dataset,
                "track": spec.track,
                "model_count": index["model_count"],
                "index_file": str(out_path.relative_to(REPO_ROOT)),
            }
        )

    (args.output_root / "all_datasets_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote dataset model indexes to {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

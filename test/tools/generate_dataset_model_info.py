#!/usr/bin/env python3
"""Generate dataset/model index JSONs from canonical object-placement JSONs."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DatasetSpec:
    dataset: str
    track: str
    json_dir: str
    prefix: str
    participant_csv_local_root: str
    participant_csv_server_root: str
    participant_csv_template: str
    mesh_local_root: str
    mesh_server_root: str
    mesh_template: str
    gt_local_root: str
    gt_server_root: str
    gt_templates: tuple[str, ...]
    gt_type: str
    output_file: str
    notes: tuple[str, ...] = ()


SPECS = [
    DatasetSpec(
        dataset="3DVA",
        track="3dva",
        json_dir="3dva_jsons",
        prefix="3DVA_",
        participant_csv_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA",
        participant_csv_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/3DVA/csv",
        participant_csv_template="{model}.csv",
        mesh_local_root="/Users/admin/Documents/LAB/Dataset/3DVA/3DModels-Simplif-up",
        mesh_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/3DVA/3DModels-Simplif-up",
        mesh_template="{model}.obj",
        gt_local_root="/Users/admin/Documents/LAB/Dataset/3DVA/FixationMaps",
        gt_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/3DVA/FixationMaps",
        gt_templates=("{model}_300norm.txt", "{model}_413norm.txt", "{model}_599norm.txt"),
        gt_type="per_vertex_static_views",
        output_file="3dva_models.json",
        notes=("3DVA GT views 300/413/599 are static-view fixation maps, not dynamic-video GT.",),
    ),
    DatasetSpec(
        dataset="MeshMamba",
        track="non_texture",
        json_dir="mamba_non_jsons",
        prefix="MeshMamba_non_texture_",
        participant_csv_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_non_texture",
        participant_csv_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/MeshMamba_non_texture/csv",
        participant_csv_template="{model}.csv",
        mesh_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/non_texture",
        mesh_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/MeshFile/non_texture",
        mesh_template="{model}/{model}.obj",
        gt_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/non_texture",
        gt_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/SaliencyMap/non_texture",
        gt_templates=("{model}.csv",),
        gt_type="per_face",
        output_file="meshmamba_non_texture_models.json",
        notes=("MeshMamba GT filenames can differ by case or dataset aliases; eval scripts use fuzzy matching.",),
    ),
    DatasetSpec(
        dataset="MeshMamba",
        track="rgb_texture",
        json_dir="mamba_rgb_jsons",
        prefix="MeshMamba_rgb_texture_",
        participant_csv_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_rgb_texture",
        participant_csv_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/MeshMamba_rgb_texture/csv",
        participant_csv_template="{model}.csv",
        mesh_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/rgb_texture",
        mesh_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/MeshFile/rgb_texture",
        mesh_template="{model}/{model}.obj",
        gt_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/rgb_texture",
        gt_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/SaliencyMap/rgb_texture",
        gt_templates=("{model}.csv",),
        gt_type="per_face",
        output_file="meshmamba_rgb_texture_models.json",
        notes=("MeshMamba GT filenames can differ by case or dataset aliases; eval scripts use fuzzy matching.",),
    ),
    DatasetSpec(
        dataset="SAL3D",
        track="sal3d",
        json_dir="sal3d_jsons",
        prefix="Sal3D_",
        participant_csv_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/SAL3D",
        participant_csv_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D",
        participant_csv_template="{model}.csv",
        mesh_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Meshes",
        mesh_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Meshes",
        mesh_template="{model}.obj",
        gt_local_root="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Gaze",
        gt_server_root="/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Gaze",
        gt_templates=("{model}.txt",),
        gt_type="per_vertex_subset_with_optional_smooth_gaze",
        output_file="sal3d_models.json",
        notes=(
            "SAL3D participant CSV count is 56 while placement JSON count is 57; gorgoile has no current CSV.",
            "Smooth_Gaze is an auxiliary GT smoothing directory, not participant JSON.",
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


def path_status(root: str, relative: str) -> dict[str, Any]:
    path = Path(root) / relative
    return {
        "path": str(path),
        "exists_on_this_machine": path.exists(),
    }


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
    return path.stem.removeprefix(prefix)


def build_dataset_index(spec: DatasetSpec, placement_root: Path) -> dict[str, Any]:
    json_root = placement_root / spec.json_dir
    models = []
    for json_path in sorted(json_root.glob("*.json")):
        model = model_from_json_name(json_path, spec.prefix)
        data = json.loads(json_path.read_text(encoding="utf-8"))

        participant_csv_rel = spec.participant_csv_template.format(model=model)
        mesh_rel = spec.mesh_template.format(model=model)
        gt_rels = [template.format(model=model) for template in spec.gt_templates]

        models.append(
            {
                "model": model,
                "model_name_in_json": data.get("model_name"),
                "placement_json": {
                    "relative_path": str(json_path.relative_to(REPO_ROOT)),
                    "sha256": sha256(json_path),
                },
                "participant_data": {
                    "format": "csv",
                    "local": path_status(spec.participant_csv_local_root, participant_csv_rel),
                    "server": {
                        "path": str(Path(spec.participant_csv_server_root) / participant_csv_rel),
                    },
                    "note": "Raw participant gaze observations are stored in CSV, not in repository JSONs.",
                },
                "mesh": {
                    "local": path_status(spec.mesh_local_root, mesh_rel),
                    "server": {
                        "path": str(Path(spec.mesh_server_root) / mesh_rel),
                    },
                },
                "ground_truth": {
                    "type": spec.gt_type,
                    "local": [path_status(spec.gt_local_root, rel) for rel in gt_rels],
                    "server": [{"path": str(Path(spec.gt_server_root) / rel)} for rel in gt_rels],
                },
                "render_and_projection": {
                    "camera_static": compact_camera(data.get("camera_static", {})),
                    "model_static": data.get("model_static", {}),
                    "animation": data.get("animation", {}),
                    "video_info": data.get("video_info", {}),
                    "frame_count": len(data.get("frames", [])),
                    "first_frame": data.get("frames", [None])[0],
                    "last_frame": data.get("frames", [None])[-1],
                },
            }
        )

    return {
        "dataset": spec.dataset,
        "track": spec.track,
        "purpose": "model-level index linking placement JSONs, participant CSVs, meshes, and GT files",
        "object_placement_json_root": str((placement_root / spec.json_dir).relative_to(REPO_ROOT)),
        "model_count": len(models),
        "participant_data_format": "csv",
        "notes": list(spec.notes),
        "models": models,
    }


def main() -> int:
    args = parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    summary = {
        "purpose": "summary of repository-local JSON organization and dataset model indexes",
        "object_placement_root": str(args.placement_root.relative_to(REPO_ROOT)),
        "dataset_model_info_root": str(args.output_root.relative_to(REPO_ROOT)),
        "participant_data_location": {
            "format": "csv",
            "local_roots": {
                spec.dataset + ":" + spec.track: spec.participant_csv_local_root
                for spec in SPECS
            },
            "server_roots": {
                spec.dataset + ":" + spec.track: spec.participant_csv_server_root
                for spec in SPECS
            },
            "note": "There are no participant-observation JSONs in the repo; repo JSONs describe camera/object placement.",
        },
        "datasets": [],
    }

    for spec in SPECS:
        index = build_dataset_index(spec, args.placement_root)
        out_path = args.output_root / spec.output_file
        out_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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

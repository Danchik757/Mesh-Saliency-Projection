#!/usr/bin/env python3
"""
Generate per-model Sal3D_{model}.json camera/animation files for SAL3D dataset.

The SAL3D render script (sal_render_1.py) uses:
  - forward_axis='Z', up_axis='Y' for OBJ import
  - Fixed camera at (0, -1.5, 0.5), looking at (0, 0, 0)
  - Object rotates around world Z; start angle deterministic via SHA256(model_name)
  - FPS=30, DURATION=24s, DEG_PER_SECOND=360/(24-2)=16.3636...
  - BBox constraints: W=0.8, D=0.8, H=0.7 (scale = min of three ratios)

Output format matches 3DVA/MeshMamba JSON so the existing Blender canonical
alignment script can consume them without modification.

Usage:
    python3 test/tools/generate_sal3d_jsons.py \
        --mesh-dir /path/to/SAL3D_Dataset/Meshes \
        --out-dir  /path/to/jsons_for_models/SAL3D_json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from datetime import datetime
from pathlib import Path

import numpy as np


# ── render script constants (must match sal_render_1.py exactly) ──────────────
FPS = 30
DURATION_SECONDS = 24
DEG_PER_SECOND = 360.0 / (DURATION_SECONDS - 2)   # 16.3636…
TOTAL_FRAMES = FPS * DURATION_SECONDS               # 720
CAMERA_DISTANCE = 1.5
CAMERA_Z_OFFSET = 0.5
H_EYE = 0.0
FOV_DEG = 60.0
CLIP_START = 0.1
CLIP_END = 100.0
RESOLUTION_X = 1920
RESOLUTION_Y = 1080
BBOX_MAX_WIDTH = 0.8
BBOX_MAX_DEPTH = 0.8
BBOX_MAX_HEIGHT = 0.7

# OBJ axis remap: forward='Z', up='Y'
# World_X =  OBJ_X
# World_Y = -OBJ_Z
# World_Z =  OBJ_Y
AXIS_REMAP = np.array([
    [1,  0,  0],
    [0,  0, -1],
    [0,  1,  0],
], dtype=np.float64)


def generate_seed(model_name: str) -> int:
    name_bytes = model_name.lower().encode("utf-8")
    h = hashlib.sha256(name_bytes).hexdigest()
    return int(h[:8], 16)


def start_angle_deg(model_name: str) -> float:
    seed = generate_seed(model_name)
    random.seed(seed)
    return random.uniform(0, 360)


def load_obj_vertices(obj_path: Path) -> np.ndarray:
    verts = []
    with open(obj_path, "r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                parts = line.split()
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return np.array(verts, dtype=np.float64)


def world_bbox(verts_obj: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (min_xyz, max_xyz) in world space after OBJ→world axis remap."""
    verts_world = verts_obj @ AXIS_REMAP.T
    return verts_world.min(axis=0), verts_world.max(axis=0)


def compute_scale(bbox_min: np.ndarray, bbox_max: np.ndarray) -> float:
    dims = bbox_max - bbox_min
    w, d, h = dims[0], dims[1], dims[2]
    sx = BBOX_MAX_WIDTH  / w if w > 1e-9 else 1.0
    sy = BBOX_MAX_DEPTH  / d if d > 1e-9 else 1.0
    sz = BBOX_MAX_HEIGHT / h if h > 1e-9 else 1.0
    return float(min(sx, sy, sz))


def camera_rotation_euler_xyz(cam_loc, target=(0.0, 0.0, 0.0)) -> list[float]:
    """
    Replicate Blender's to_track_quat('-Z','Y').to_euler() for a camera
    placed at cam_loc looking toward target.

    Returns [rx, ry, rz] in radians (Blender XYZ Euler order).
    """
    cam = np.array(cam_loc, dtype=np.float64)
    tgt = np.array(target, dtype=np.float64)
    direction = tgt - cam
    direction /= np.linalg.norm(direction)

    # Camera local +Z = -direction (camera looks along -Z)
    z_cam = -direction

    # Camera local +Y ≈ world Y, projected orthogonal to z_cam
    y_world = np.array([0.0, 1.0, 0.0])
    y_cam = y_world - np.dot(y_world, z_cam) * z_cam
    norm = np.linalg.norm(y_cam)
    if norm < 1e-9:
        y_cam = np.array([0.0, 0.0, 1.0])
    else:
        y_cam /= norm

    # Camera local +X = Y × Z
    x_cam = np.cross(y_cam, z_cam)
    x_cam /= np.linalg.norm(x_cam)

    # Rotation matrix: columns are local axes expressed in world space
    R = np.column_stack([x_cam, y_cam, z_cam])

    # Decompose R into XYZ Euler (Blender convention)
    sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    if sy > 1e-6:
        rx = math.atan2(R[2, 1], R[2, 2])
        ry = math.atan2(-R[2, 0], sy)
        rz = math.atan2(R[1, 0], R[0, 0])
    else:
        rx = math.atan2(-R[1, 2], R[1, 1])
        ry = math.atan2(-R[2, 0], sy)
        rz = 0.0

    return [rx, ry, rz]


def build_json(model_name: str, obj_path: Path) -> dict:
    verts = load_obj_vertices(obj_path)
    bbox_min, bbox_max = world_bbox(verts)
    bbox_center = (bbox_min + bbox_max) / 2.0
    scale = compute_scale(bbox_min, bbox_max)

    cam_loc = [0.0, -CAMERA_DISTANCE, H_EYE + CAMERA_Z_OFFSET]
    cam_rot = camera_rotation_euler_xyz(cam_loc, target=[0.0, 0.0, H_EYE])
    fov_rad = math.radians(FOV_DEG)
    aspect = RESOLUTION_X / RESOLUTION_Y
    f = 1.0 / math.tan(fov_rad / 2.0)
    near, far = CLIP_START, CLIP_END
    proj = [
        [f / aspect, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, -(far + near) / (far - near), -(2 * far * near) / (far - near)],
        [0, 0, -1, 0],
    ]

    ang_deg = start_angle_deg(model_name)

    frames = []
    for frame in range(1, TOTAL_FRAMES + 1):
        t = (frame - 1) / FPS
        rot_z_deg = ang_deg + t * DEG_PER_SECOND
        frames.append({
            "frame": frame,
            "timestamp": round(t, 6),
            "rotation_z_radians": round(math.radians(rot_z_deg), 8),
            "rotation_z_degrees": round(rot_z_deg, 6),
        })

    return {
        "model_name": model_name,
        "file_version": "1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "generated_by": "generate_sal3d_jsons.py (local, deterministic)",

        "video_info": {
            "fps": FPS,
            "duration_seconds": DURATION_SECONDS,
            "total_frames": TOTAL_FRAMES,
            "resolution_width": RESOLUTION_X,
            "resolution_height": RESOLUTION_Y,
            "aspect_ratio": round(aspect, 6),
        },

        "camera_static": {
            "location": cam_loc,
            "rotation_euler_radians": cam_rot,
            "rotation_euler_degrees": [math.degrees(v) for v in cam_rot],
            "fov_radians": round(fov_rad, 8),
            "fov_degrees": FOV_DEG,
            "lens_mm": 26.0,
            "sensor_width_mm": 36.0,
            "sensor_height_mm": 24.0,
            "clip_start": CLIP_START,
            "clip_end": CLIP_END,
            "projection_matrix": proj,
        },

        "model_static": {
            "location": [0.0, 0.0, H_EYE],
            "scale": [scale, scale, scale],
            "bbox_center_obj_space": bbox_center.tolist(),
            "bbox_max_dimensions": {
                "width": BBOX_MAX_WIDTH,
                "depth": BBOX_MAX_DEPTH,
                "height": BBOX_MAX_HEIGHT,
            },
        },

        "animation": {
            "start_angle_degrees": round(ang_deg, 6),
            "start_angle_radians": round(math.radians(ang_deg), 8),
            "rotation_speed_deg_per_sec": round(DEG_PER_SECOND, 6),
            "rotation_speed_rad_per_sec": round(math.radians(DEG_PER_SECOND), 8),
            "rotation_axis": "Z",
            "rotation_direction": "counter_clockwise",
        },

        "frames": frames,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Sal3D JSON camera files for all SAL3D models.")
    parser.add_argument(
        "--mesh-dir",
        type=Path,
        default=Path(
            "/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Meshes"
        ),
        help="Directory containing SAL3D .obj files.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(
            "/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/SAL3D_json"
        ),
        help="Output directory for Sal3D_{model}.json files.",
    )
    parser.add_argument("--models", nargs="*", default=None, help="Subset of models (default: all).")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    obj_files = sorted(args.mesh_dir.glob("*.obj"))
    if args.models:
        obj_files = [f for f in obj_files if f.stem in args.models]

    print(f"Generating JSON for {len(obj_files)} models → {args.out_dir}")
    for obj_path in obj_files:
        model_name = obj_path.stem
        out_path = args.out_dir / f"Sal3D_{model_name}.json"
        print(f"  {model_name} ...", end=" ", flush=True)
        data = build_json(model_name, obj_path)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print(f"scale={data['model_static']['scale'][0]:.4f}  "
              f"start={data['animation']['start_angle_degrees']:.1f}°  → {out_path.name}")

    print("Done.")


if __name__ == "__main__":
    main()

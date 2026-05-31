#!/usr/bin/env python3
"""
Render one frame of bunny at CAMERA_DISTANCE = 1 and 3.

Writes temporary JSONs (with modified camera location/rotation) and manifests,
then invokes Blender for each distance.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_JSON = Path(
    "/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/SAL3D_json/Sal3D_bunny.json"
)
OBJ_PATH = Path(
    "/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/3DVA/models/bunny.obj"
)
OUT_DIR = REPO_ROOT / "test/output_local/preview_checks/SAL3D"
TMP_JSON_DIR = REPO_ROOT / "test/tmp_manifests"
TMP_MANIFEST_DIR = REPO_ROOT / "test/tmp_manifests"
RENDER_SCRIPT = REPO_ROOT / "test/blender_canonical/render_preview_from_manifest_blender.py"
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")

DISTANCES = [1, 3]
H_EYE = 0.0
CAMERA_Z_OFFSET = 0.5
FRAME_INDEX = 0


def camera_rotation_euler_xyz(cam_loc, target=(0.0, 0.0, 0.0)):
    cam = np.array(cam_loc, dtype=np.float64)
    tgt = np.array(target, dtype=np.float64)
    direction = tgt - cam
    direction /= np.linalg.norm(direction)
    z_cam = -direction
    y_world = np.array([0.0, 1.0, 0.0])
    y_cam = y_world - np.dot(y_world, z_cam) * z_cam
    norm = np.linalg.norm(y_cam)
    y_cam = np.array([0.0, 0.0, 1.0]) if norm < 1e-9 else y_cam / norm
    x_cam = np.cross(y_cam, z_cam)
    x_cam /= np.linalg.norm(x_cam)
    R = np.column_stack([x_cam, y_cam, z_cam])
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


def make_json_for_distance(base: dict, dist: float) -> dict:
    import copy
    data = copy.deepcopy(base)
    cam_loc = [0.0, -dist, H_EYE + CAMERA_Z_OFFSET]
    cam_rot = camera_rotation_euler_xyz(cam_loc, target=[0.0, 0.0, H_EYE])
    data["camera_static"]["location"] = cam_loc
    data["camera_static"]["rotation_euler_radians"] = cam_rot
    data["camera_static"]["rotation_euler_degrees"] = [math.degrees(v) for v in cam_rot]
    return data


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_JSON_DIR.mkdir(parents=True, exist_ok=True)

    with open(BASE_JSON, encoding="utf-8") as f:
        base = json.load(f)

    for dist in DISTANCES:
        tag = f"bunny_camdist{dist}"

        # write modified JSON
        modified = make_json_for_distance(base, dist)
        json_path = TMP_JSON_DIR / f"{tag}_camera.json"
        json_path.write_text(json.dumps(modified, indent=2), encoding="utf-8")

        # write manifest
        manifest = {
            "dataset": "SAL3D",
            "model": "bunny",
            "obj_path": str(OBJ_PATH),
            "json_path": str(json_path),
            "output_prefix": str(OUT_DIR / tag),
            "frame_index": FRAME_INDEX,
            "resolution_scale": 0.5,
            "recenter_to_bbox_center": True,
            "extra_rotate_x_deg": 90.0,
            "override_fov_deg": None,
            "forward_axis": "Z",
            "up_axis": "Y",
        }
        manifest_path = TMP_MANIFEST_DIR / f"{tag}_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print(f"\n--- Rendering CAMERA_DISTANCE={dist} ---")
        print(f"  cam_loc : {modified['camera_static']['location']}")
        print(f"  cam_rot : {[round(v, 5) for v in modified['camera_static']['rotation_euler_radians']]}")
        print(f"  output  : {OUT_DIR / tag}_blender.png")

        cmd = [
            str(BLENDER),
            "--background",
            "--python", str(RENDER_SCRIPT),
            "--", "--manifest", str(manifest_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("STDERR:", result.stderr[-2000:])
            sys.exit(1)
        # extract JSON report from stdout
        for line in result.stdout.splitlines():
            if line.startswith("{"):
                try:
                    report = json.loads(line)
                    print(f"  rendered: {report.get('rendered_preview')}")
                except json.JSONDecodeError:
                    pass

    print("\nDone. Check test/output_local/preview_checks/SAL3D/")


if __name__ == "__main__":
    main()

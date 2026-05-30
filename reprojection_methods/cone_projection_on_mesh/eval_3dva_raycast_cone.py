#!/usr/bin/env python3
"""
Evaluate two gaze-to-mesh transfer methods on one 3DVA model.

Methods:
1. raycast_nearest_vertex:
   Cast the gaze ray through each screen point and assign the hit to the
   nearest vertex of the intersected triangle.
2. cone_gaussian_on_mesh:
   Use the same ray hit, but spread its contribution to nearby vertices with
   a Gaussian whose world-space sigma comes from the angular uncertainty.

The script reads gaze trajectories from CSV, camera/animation from JSON, OBJ
from the 3DVA dataset root, and compares the produced per-vertex maps against
FixationMaps ground truth (views 300, 413, 599).

Env vars (used when CLI args are not provided):
  VISUAL_ATTENTION_3D_SHAPES_ROOT   — root of the 3DVA dataset
  THREE_DVA_CSV_ROOT                — directory with per-model CSV files
  THREE_DVA_JSON_ROOT               — directory with per-model JSON files
  THREE_DVA_OUTPUT_DIR              — output directory
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import trimesh
from scipy.spatial import cKDTree
from scipy.spatial.distance import cosine
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

WIDTH = 1920
HEIGHT = 1080


@dataclass
class FrameGazeBatch:
    x_norm: np.ndarray
    y_norm: np.ndarray


def _env_path(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var, fallback))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate raycast_nearest_vertex and cone_gaussian_on_mesh on one 3DVA model."
    )
    parser.add_argument("--model", default="bunny", help="3DVA model name, e.g. bunny or A380.")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("VISUAL_ATTENTION_3D_SHAPES_ROOT", "e.g. /srv/datasets/3DVA"),
        help="Root of the 3DVA dataset (3DModels-Simplif, FixationMaps, ...).",
    )
    parser.add_argument(
        "--csv-root",
        type=Path,
        default=_env_path("THREE_DVA_CSV_ROOT", "e.g. /srv/side_inputs/3DVA/csv"),
        help="Directory with per-model 3DVA CSV gaze files.",
    )
    parser.add_argument(
        "--json-root",
        type=Path,
        default=_env_path("THREE_DVA_JSON_ROOT", "e.g. /srv/side_inputs/3DVA/json"),
        help="Directory with per-model 3DVA JSON camera/animation files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_env_path(
            "THREE_DVA_OUTPUT_DIR",
            str(REPO_ROOT / "results" / "3dva" / "raycast_cone"),
        ),
        help="Output directory for maps and the evaluation report.",
    )
    parser.add_argument(
        "--sigma-deg",
        type=float,
        default=1.0,
        help="Angular sigma in degrees for the cone-style Gaussian.",
    )
    parser.add_argument(
        "--radius-sigma-mult",
        type=float,
        default=3.0,
        help="Query-radius multiplier for the cone-style Gaussian kernel.",
    )
    parser.add_argument(
        "--recenter-to-bbox-center",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Recenter OBJ vertices to bounding-box center before scale/rotation.",
    )
    parser.add_argument(
        "--base-rotate-z-deg",
        type=float,
        default=0.0,
        help="Static Z correction applied before scale/animation, e.g. to match Blender OBJ import axes.",
    )
    parser.add_argument(
        "--extra-rotate-x-deg",
        type=float,
        default=0.0,
        help="Extra runtime X rotation in degrees (applied after Z rotation).",
    )
    parser.add_argument(
        "--extra-rotate-y-deg",
        type=float,
        default=0.0,
        help="Extra runtime Y rotation in degrees (applied after extra X rotation).",
    )
    parser.add_argument(
        "--override-fov-deg",
        type=float,
        default=None,
        help="Override JSON FOV for projection matrix only.",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Output sub-directory tag. Auto-derived from transform params if omitted.",
    )
    return parser.parse_args()


def resolve_model_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "csv":    args.csv_root  / f"{args.model}.csv",
        "json":   args.json_root / f"3DVA_{args.model}.json",
        "obj":    args.dataset_root / "3DModels-Simplif" / f"{args.model}.obj",
        "gt_300": args.dataset_root / "FixationMaps" / f"{args.model}_300norm.txt",
        "gt_413": args.dataset_root / "FixationMaps" / f"{args.model}_413norm.txt",
        "gt_599": args.dataset_root / "FixationMaps" / f"{args.model}_599norm.txt",
    }


def ensure_exists(paths: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))


def load_gaze_batches(
    csv_path: Path, fps: int, total_frames: int
) -> tuple[dict[int, FrameGazeBatch], dict[str, int]]:
    df = pd.read_csv(csv_path)
    per_frame_x: dict[int, list[float]] = defaultdict(list)
    per_frame_y: dict[int, list[float]] = defaultdict(list)
    total_points = 0

    for _, row in df.iterrows():
        gaze = ast.literal_eval(row["data_gazes"])
        for t, x, y in zip(gaze.get("t", []), gaze.get("x", []), gaze.get("y", [])):
            x, y = float(x), float(y)
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                continue
            frame = min(int(math.floor(float(t) * fps)), total_frames - 1)
            per_frame_x[frame].append(x)
            per_frame_y[frame].append(y)
            total_points += 1

    batches = {
        frame: FrameGazeBatch(
            x_norm=np.asarray(per_frame_x[frame], dtype=np.float64),
            y_norm=np.asarray(per_frame_y[frame], dtype=np.float64),
        )
        for frame in sorted(per_frame_x)
    }
    stats = {
        "num_rows": int(len(df)),
        "num_participants": int(df["participation_id"].nunique()),
        "num_points": int(total_points),
        "num_frames_with_points": int(len(batches)),
    }
    return batches, stats


def build_projection_matrix_from_fov(
    fov_deg: float, aspect_ratio: float, clip_start: float, clip_end: float
) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    near, far = float(clip_start), float(clip_end)
    return np.array(
        [
            [f / aspect_ratio, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, -(far + near) / (far - near), -(2 * far * near) / (far - near)],
            [0, 0, -1, 0],
        ],
        dtype=np.float64,
    )


def apply_model_transform(
    vertices: np.ndarray,
    camera_data: dict,
    rotation_z_rad: float,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
) -> np.ndarray:
    v = np.asarray(vertices, dtype=np.float64).copy()
    rz0 = math.radians(base_rotate_z_deg)
    if abs(rz0) > 1e-12:
        cz0, sz0 = math.cos(rz0), math.sin(rz0)
        x0 = cz0 * v[:, 0] - sz0 * v[:, 1]
        y0 = sz0 * v[:, 0] + cz0 * v[:, 1]
        v[:, 0], v[:, 1] = x0, y0
    if recenter_to_bbox_center:
        v -= 0.5 * (v.min(axis=0) + v.max(axis=0))

    scale = np.asarray(camera_data["model_static"]["scale"], dtype=np.float64)
    v *= scale

    ca, sa = math.cos(rotation_z_rad), math.sin(rotation_z_rad)
    x2 = ca * v[:, 0] - sa * v[:, 1]
    y2 = sa * v[:, 0] + ca * v[:, 1]
    v[:, 0], v[:, 1] = x2, y2

    rx = math.radians(extra_rotate_x_deg)
    if abs(rx) > 1e-12:
        crx, srx = math.cos(rx), math.sin(rx)
        y3 = crx * v[:, 1] - srx * v[:, 2]
        z3 = srx * v[:, 1] + crx * v[:, 2]
        v[:, 1], v[:, 2] = y3, z3

    ry = math.radians(extra_rotate_y_deg)
    if abs(ry) > 1e-12:
        cry, sry = math.cos(ry), math.sin(ry)
        x4 = cry * v[:, 0] + sry * v[:, 2]
        z4 = -sry * v[:, 0] + cry * v[:, 2]
        v[:, 0], v[:, 2] = x4, z4

    v += np.asarray(camera_data["model_static"]["location"], dtype=np.float64)
    return v


def screen_to_rays(
    camera_data: dict,
    x_norm: np.ndarray,
    y_norm: np.ndarray,
    projection_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    ndc_x = x_norm * 2.0 - 1.0
    ndc_y = -(y_norm * 2.0 - 1.0)
    ones = np.ones_like(ndc_x)

    ndc_near = np.stack([ndc_x, ndc_y, -ones, ones], axis=1)
    ndc_far  = np.stack([ndc_x, ndc_y,  ones, ones], axis=1)

    view_matrix = np.asarray(
        camera_data["camera_static"]["view_matrix"], dtype=np.float64
    ).reshape(4, 4)
    inv_proj = np.linalg.inv(projection_matrix)
    inv_view = np.linalg.inv(view_matrix)

    cam_near = (inv_proj @ ndc_near.T).T
    cam_near /= cam_near[:, 3:4]
    cam_far  = (inv_proj @ ndc_far.T).T
    cam_far  /= cam_far[:, 3:4]

    world_near = (inv_view @ cam_near.T).T
    world_far  = (inv_view @ cam_far.T).T

    origins    = world_near[:, :3]
    directions = world_far[:, :3] - world_near[:, :3]
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    return origins, directions


def scale_like_fixation_map(values: np.ndarray) -> np.ndarray:
    mx = float(values.max())
    return (values / mx * 7.0) if mx > 0 else values.copy()


def compute_metrics(pred: np.ndarray, gt: np.ndarray) -> dict[str, float]:
    lcc, lcc_p = pearsonr(pred, gt)
    spearman_r, spearman_p = spearmanr(pred, gt)

    gt_nonzero = gt[gt > 0]
    if len(gt_nonzero) > 0:
        threshold  = np.median(gt_nonzero)
        gt_binary  = (gt > threshold).astype(int)
        auc = float(roc_auc_score(gt_binary, pred)) if len(np.unique(gt_binary)) > 1 else 0.5
    else:
        auc = 0.5

    eps = 1e-10
    pred_p = pred / (pred.sum() + eps) + eps
    gt_p   = gt   / (gt.sum()   + eps) + eps
    kld    = float(np.sum(gt_p * np.log(gt_p / pred_p)))
    sim    = float(np.sum(np.minimum(pred / (pred.sum() + eps), gt / (gt.sum() + eps))))

    return {
        "CC":      float(lcc),
        "LCC":     float(lcc),
        "AUC":     auc,
        "KLD":     kld,
        "SIM":     sim,
        "Spearman": float(spearman_r),
        "MSE":     float(np.mean((pred - gt) ** 2)),
        "MAE":     float(np.mean(np.abs(pred - gt))),
        "Cosine":  float(1.0 - cosine(pred, gt)) if pred.sum() > 0 and gt.sum() > 0 else 0.0,
    }


def run_methods(
    mesh: trimesh.Trimesh,
    camera_data: dict,
    gaze_batches: dict[int, FrameGazeBatch],
    sigma_deg: float,
    radius_sigma_mult: float,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    override_fov_deg: float | None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    n_verts = len(mesh.vertices)
    raycast_counts = np.zeros(n_verts, dtype=np.float64)
    cone_counts    = np.zeros(n_verts, dtype=np.float64)

    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]
    if override_fov_deg is not None:
        proj_mat = build_projection_matrix_from_fov(
            override_fov_deg, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]
        )
    else:
        proj_mat = np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4)

    total_points = total_hits = total_cone_v = 0

    frames_list = camera_data["frames"]
    for frame, batch in gaze_batches.items():
        if batch.x_norm.size == 0:
            continue
        if frame >= len(frames_list):
            continue
        rot_z = float(frames_list[frame]["rotation_z_radians"])

        xmesh = mesh.copy()
        xmesh.vertices = apply_model_transform(
            mesh.vertices,
            camera_data,
            rot_z,
            recenter_to_bbox_center,
            base_rotate_z_deg,
            extra_rotate_x_deg,
            extra_rotate_y_deg,
        )

        origins, dirs = screen_to_rays(camera_data, batch.x_norm, batch.y_norm, proj_mat)
        locs, idx_ray, idx_tri = xmesh.ray.intersects_location(
            ray_origins=origins, ray_directions=dirs, multiple_hits=False
        )

        total_points += int(batch.x_norm.size)
        if len(locs) == 0:
            continue

        hit_pts = np.asarray(locs, dtype=np.float64)
        tri_idx  = np.asarray(idx_tri, dtype=np.int64)
        ray_idx  = np.asarray(idx_ray, dtype=np.int64)

        # raycast_nearest_vertex
        tri_verts = xmesh.faces[tri_idx]
        tri_coords = xmesh.vertices[tri_verts]
        dists = np.linalg.norm(tri_coords - hit_pts[:, None, :], axis=2)
        nearest_local = np.argmin(dists, axis=1)
        nearest_v = tri_verts[np.arange(len(tri_verts)), nearest_local]
        np.add.at(raycast_counts, nearest_v, 1.0)

        # cone_gaussian_on_mesh
        vtree = cKDTree(xmesh.vertices)
        origins_at_hit = origins[ray_idx]
        depth = np.linalg.norm(hit_pts - origins_at_hit, axis=1)
        sigma_world = np.maximum(depth * math.tan(math.radians(sigma_deg)), 1e-6)
        for pt, sigma in zip(hit_pts, sigma_world):
            idxs = vtree.query_ball_point(pt, r=radius_sigma_mult * sigma) or [int(vtree.query(pt)[1])]
            lv = xmesh.vertices[np.asarray(idxs, dtype=np.int64)]
            w  = np.exp(-0.5 * np.sum((lv - pt) ** 2, axis=1) / sigma ** 2)
            cone_counts[np.asarray(idxs, dtype=np.int64)] += w
            total_cone_v += len(idxs)

        total_hits += len(hit_pts)

    stats = {
        "total_gaze_points":  total_points,
        "successful_hits":    total_hits,
        "hit_rate":           total_hits / total_points if total_points else 0.0,
        "raycast_nonzero_vertices": int(np.count_nonzero(raycast_counts)),
        "cone_nonzero_vertices":    int(np.count_nonzero(cone_counts)),
    }
    return raycast_counts, cone_counts, stats


def main() -> None:
    args  = parse_args()
    paths = resolve_model_paths(args)
    ensure_exists(paths)

    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)
    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected a single Trimesh, got {type(mesh)}")

    gaze_batches, gaze_stats = load_gaze_batches(
        paths["csv"],
        fps=int(camera_data["video_info"]["fps"]),
        total_frames=int(camera_data["video_info"]["total_frames"]),
    )

    tag_parts = []
    if args.recenter_to_bbox_center:
        tag_parts.append("recenter")
    if abs(args.base_rotate_z_deg) > 1e-12:
        tag_parts.append(f"baserz{args.base_rotate_z_deg}".replace(".", "p"))
    if abs(args.extra_rotate_x_deg) > 1e-12:
        tag_parts.append(f"rotx{args.extra_rotate_x_deg}".replace(".", "p"))
    if abs(args.extra_rotate_y_deg) > 1e-12:
        tag_parts.append(f"roty{args.extra_rotate_y_deg}".replace(".", "p"))
    if args.override_fov_deg is not None:
        tag_parts.append(f"fov{args.override_fov_deg}".replace(".", "p"))
    tag = args.tag or ("default" if not tag_parts else "_".join(tag_parts))

    raycast, cone, run_stats = run_methods(
        mesh=mesh,
        camera_data=camera_data,
        gaze_batches=gaze_batches,
        sigma_deg=args.sigma_deg,
        radius_sigma_mult=args.radius_sigma_mult,
        recenter_to_bbox_center=bool(args.recenter_to_bbox_center),
        base_rotate_z_deg=args.base_rotate_z_deg,
        extra_rotate_x_deg=args.extra_rotate_x_deg,
        extra_rotate_y_deg=args.extra_rotate_y_deg,
        override_fov_deg=args.override_fov_deg,
    )

    raycast_fix = scale_like_fixation_map(raycast)
    cone_fix    = scale_like_fixation_map(cone)

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_raycast_norm.txt", raycast_fix, fmt="%.10f")
    np.savetxt(out_dir / f"{args.model}_cone_norm.txt",    cone_fix,    fmt="%.10f")

    gt_maps = {v: np.loadtxt(paths[f"gt_{v}"]) for v in ("300", "413", "599")}
    results = {
        "raycast_nearest_vertex": {v: compute_metrics(raycast_fix, gt) for v, gt in gt_maps.items()},
        "cone_gaussian_on_mesh":  {v: compute_metrics(cone_fix,    gt) for v, gt in gt_maps.items()},
    }

    report = {
        "model":   args.model,
        "tag":     tag,
        "dataset": "3DVA",
        "gaze_stats":  gaze_stats,
        "run_stats":   run_stats,
        "method_params": {
            "sigma_deg":              args.sigma_deg,
            "radius_sigma_mult":      args.radius_sigma_mult,
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg":      args.base_rotate_z_deg,
            "extra_rotate_x_deg":     args.extra_rotate_x_deg,
            "extra_rotate_y_deg":     args.extra_rotate_y_deg,
            "override_fov_deg":       args.override_fov_deg,
            "transform_order": "base_rotate_z -> recenter -> scale -> rotation_z -> extra_rotate_x -> extra_rotate_y -> translation",
        },
        "metrics_vs_gt": results,
    }

    report_path = out_dir / f"{args.model}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()

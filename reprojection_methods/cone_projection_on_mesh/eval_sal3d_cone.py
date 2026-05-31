#!/usr/bin/env python3
"""
Evaluate raycast_nearest_vertex and cone_gaussian_on_mesh on one SAL3D model.

GT format:
  SAL3D_Dataset/Gaze/<model>.txt  —  20000×8 text file
  columns: x y z  nx ny nz  smooth_saliency  binary_saliency
  The rows correspond to vertices in a DIFFERENT order than the OBJ file.
  We match Gaze rows to OBJ vertices by nearest-neighbor (exact, dist=0).

Transform recipe (validated with Blender canonical preview, IoU≥0.977):
  forward_axis='Z', up_axis='Y' in Blender OBJ import → implicit Rx(90°)
  → use: --recenter-to-bbox-center --extra-rotate-x-deg 90.0
          --projection-fov-mode horizontal_to_vertical
          --transform-order blender_rig

JSON prefix:  Sal3D_<model>.json
OBJ path:     SAL3D_Dataset/Meshes/<model>.obj

Env vars:
  SAL3D_DATASET_ROOT   — root containing Gaze/, Meshes/, Smooth_Gaze/
  SAL3D_CSV_ROOT       — directory with per-model CSV gaze files (our participants)
  SAL3D_JSON_ROOT      — directory with per-model Sal3D_<model>.json files
  SAL3D_OUTPUT_DIR     — output directory
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import trimesh
from scipy.spatial import cKDTree
from scipy.stats import pearsonr, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class FrameGazeBatch:
    x_norm: np.ndarray
    y_norm: np.ndarray


def _env_path(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var, fallback))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate raycast_nearest_vertex and cone_gaussian_on_mesh on one SAL3D model."
    )
    parser.add_argument("--model", default="bunny", help="SAL3D model name (e.g. bunny, dragon, A380).")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("SAL3D_DATASET_ROOT", "e.g. /srv/datasets/SAL3D/SAL3D_Dataset"),
        help="Root of SAL3D_Dataset containing Gaze/, Meshes/, Smooth_Gaze/.",
    )
    parser.add_argument(
        "--csv-root",
        type=Path,
        default=_env_path("SAL3D_CSV_ROOT", "e.g. /srv/side_inputs/SAL3D/csv"),
        help="Directory with per-model SAL3D CSV gaze files (our experiment).",
    )
    parser.add_argument(
        "--json-root",
        type=Path,
        default=_env_path("SAL3D_JSON_ROOT", "e.g. /srv/side_inputs/SAL3D/json"),
        help="Directory with per-model Sal3D_<model>.json camera/animation files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_env_path(
            "SAL3D_OUTPUT_DIR",
            str(REPO_ROOT / "results" / "sal3d" / "cone_raycast"),
        ),
        help="Output directory for saliency maps and the evaluation report.",
    )
    parser.add_argument(
        "--gt-column",
        type=int,
        default=6,
        choices=[6, 7],
        help="Column index in Gaze/*.txt to use as GT: 6=smooth_saliency (default), 7=binary.",
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
        help="Query-radius multiplier for the cone Gaussian kernel.",
    )
    parser.add_argument(
        "--recenter-to-bbox-center",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Recenter OBJ vertices to bounding-box center before scale/rotation.",
    )
    parser.add_argument(
        "--base-rotate-z-deg",
        type=float,
        default=0.0,
        help="Static Z correction applied before scale/animation.",
    )
    parser.add_argument(
        "--extra-rotate-x-deg",
        type=float,
        default=90.0,
        help="Extra X rotation in degrees. Default 90° replicates Blender's Z-forward Y-up OBJ import.",
    )
    parser.add_argument(
        "--extra-rotate-y-deg",
        type=float,
        default=0.0,
        help="Extra Y rotation in degrees.",
    )
    parser.add_argument(
        "--override-fov-deg",
        type=float,
        default=None,
        help="Override JSON FOV. Leave None to use JSON fov_degrees (60°).",
    )
    parser.add_argument(
        "--projection-fov-mode",
        choices=["vertical", "horizontal_to_vertical", "json"],
        default="horizontal_to_vertical",
        help=(
            "How to interpret FOV for the projection matrix. "
            "Default 'horizontal_to_vertical' treats JSON fov_degrees (60°) as horizontal "
            "and converts to correct vertical FOV (~35.98°)."
        ),
    )
    parser.add_argument(
        "--transform-order",
        choices=["eval", "blender_rig"],
        default="blender_rig",
        help=(
            "Mesh transform order. Default 'blender_rig' matches the Blender render: "
            "local rotations (recenter→scale→extraX→extraY→baseZ) before per-frame animZ."
        ),
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Output sub-directory tag. Auto-derived from params if omitted.",
    )
    return parser.parse_args()


# ── path resolution ──────────────────────────────────────────────────────────

def _candidate_model_names(model: str) -> list[str]:
    raw = model.strip()
    variants = [raw, raw.lower(), raw.upper(),
                raw.replace("_", "-"), raw.replace("-", "_")]
    deduped: list[str] = []
    seen: set[str] = set()
    for v in variants:
        if v.lower() not in seen:
            deduped.append(v)
            seen.add(v.lower())
    return deduped


def _casefold_lookup(directory: Path, suffix: str) -> dict[str, Path]:
    return {
        p.name.lower(): p
        for p in sorted(directory.glob(f"*{suffix}"))
        if p.is_file()
    }


def _resolve(directory: Path, names: list[str], suffix: str) -> Path | None:
    idx = _casefold_lookup(directory, suffix)
    for name in names:
        hit = idx.get(f"{name}{suffix}".lower())
        if hit is not None:
            return hit
    return None


def resolve_model_paths(args: argparse.Namespace) -> dict[str, Path]:
    names = _candidate_model_names(args.model)

    obj_path = _resolve(args.dataset_root / "Meshes", names, ".obj")
    if obj_path is None:
        raise FileNotFoundError(
            f"OBJ not found for '{args.model}' in {args.dataset_root / 'Meshes'}"
        )

    gt_path = _resolve(args.dataset_root / "Gaze", names, ".txt")
    if gt_path is None:
        raise FileNotFoundError(
            f"Gaze GT not found for '{args.model}' in {args.dataset_root / 'Gaze'}"
        )

    csv_path = _resolve(args.csv_root, names, ".csv")
    if csv_path is None:
        raise FileNotFoundError(
            f"CSV not found for '{args.model}' in {args.csv_root}"
        )

    json_names = [f"Sal3D_{n}" for n in names]
    json_path = _resolve(args.json_root, json_names, ".json")
    if json_path is None:
        raise FileNotFoundError(
            f"JSON not found for '{args.model}' (prefix Sal3D_) in {args.json_root}"
        )

    return {"obj": obj_path, "gt": gt_path, "csv": csv_path, "json": json_path}


def ensure_exists(paths: dict[str, Path]) -> None:
    missing = [f"{k}: {v}" for k, v in paths.items() if not v.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))


# ── GT loading with vertex re-ordering ───────────────────────────────────────

def load_gt_aligned_to_obj(
    gaze_txt: Path, mesh_vertices: np.ndarray, gt_column: int
) -> np.ndarray:
    """Load GT saliency from Gaze/*.txt and align to OBJ vertex order.

    The Gaze file stores vertices in a different order than the OBJ file.
    We match each Gaze row to the nearest OBJ vertex (dist=0 for valid data).

    Returns:
        gt: (N_vertices,) float array aligned to OBJ vertex indices.
    """
    data = np.loadtxt(gaze_txt)          # (N, 8)
    gaze_xyz = data[:, :3]               # columns 0-2: vertex positions
    gaze_sal = data[:, gt_column]        # column 6 or 7: saliency

    n_verts = len(mesh_vertices)
    n_gaze  = len(gaze_xyz)

    # Gaze rows may be a strict subset of OBJ vertices (the GT was computed on a
    # 20K simplified pointcloud while the OBJ may have more vertices).
    # We allow n_gaze <= n_verts; unmatched OBJ vertices receive GT = 0.
    if n_gaze > n_verts:
        raise ValueError(
            f"GT row count ({n_gaze}) > OBJ vertex count ({n_verts}). "
            "Cannot align GT to mesh."
        )

    tree = cKDTree(mesh_vertices)
    dists, idxs = tree.query(gaze_xyz, k=1)
    if dists.max() > 1e-4:
        raise ValueError(
            f"GT vertex mismatch: max nearest-neighbor dist = {dists.max():.6f} "
            "(expected 0 — GT and OBJ may be different meshes)"
        )

    gt = np.zeros(n_verts, dtype=np.float64)
    gt[idxs] = gaze_sal
    return gt


# ── gaze loading (same format as 3DVA / MeshMamba) ───────────────────────────

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
        fr: FrameGazeBatch(
            x_norm=np.asarray(per_frame_x[fr], dtype=np.float64),
            y_norm=np.asarray(per_frame_y[fr], dtype=np.float64),
        )
        for fr in sorted(per_frame_x)
    }
    stats = {
        "num_rows":               int(len(df)),
        "num_participants":       int(df["participation_id"].nunique()),
        "num_points":             int(total_points),
        "num_frames_with_points": int(len(batches)),
    }
    return batches, stats


# ── projection matrix ─────────────────────────────────────────────────────────

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


def horizontal_to_vertical_fov_deg(h_fov_deg: float, aspect_ratio: float) -> float:
    return math.degrees(
        2.0 * math.atan(math.tan(math.radians(h_fov_deg) * 0.5) / float(aspect_ratio))
    )


def resolve_projection_matrix(
    camera_data: dict, override_fov_deg: float | None, mode: str
) -> tuple[np.ndarray, dict]:
    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]

    if mode == "json":
        return np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4), {
            "projection_fov_mode": "json",
            "input_fov_deg": None,
            "effective_vertical_fov_deg": None,
        }

    if mode == "vertical":
        if override_fov_deg is None:
            return np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4), {
                "projection_fov_mode": "vertical",
                "input_fov_deg": None,
                "effective_vertical_fov_deg": None,
            }
        eff = float(override_fov_deg)
        return build_projection_matrix_from_fov(eff, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]), {
            "projection_fov_mode": "vertical",
            "input_fov_deg": eff,
            "effective_vertical_fov_deg": eff,
        }

    if mode == "horizontal_to_vertical":
        if override_fov_deg is not None:
            h_fov = float(override_fov_deg)
            src = "override_fov_deg"
        elif "fov_degrees" in cam:
            h_fov = float(cam["fov_degrees"])
            src = "json_fov_degrees"
        else:
            h_fov = math.degrees(float(cam["fov_radians"]))
            src = "json_fov_radians"
        eff = horizontal_to_vertical_fov_deg(h_fov, float(vi["aspect_ratio"]))
        return build_projection_matrix_from_fov(eff, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]), {
            "projection_fov_mode": "horizontal_to_vertical",
            "input_fov_deg": h_fov,
            "effective_vertical_fov_deg": eff,
            "fov_source": src,
        }

    raise ValueError(f"Unknown projection_fov_mode: {mode}")


# ── mesh transform ─────────────────────────────────────────────────────────────

def apply_model_transform(
    vertices: np.ndarray,
    camera_data: dict,
    rotation_z_rad: float,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    transform_order: str,
) -> np.ndarray:
    v = np.asarray(vertices, dtype=np.float64).copy()
    bbox_center = 0.5 * (v.min(axis=0) + v.max(axis=0))

    def rz(pts: np.ndarray, rad: float) -> np.ndarray:
        if abs(rad) <= 1e-12:
            return pts
        out = pts.copy()
        c, s = math.cos(rad), math.sin(rad)
        out[:, 0] = c * pts[:, 0] - s * pts[:, 1]
        out[:, 1] = s * pts[:, 0] + c * pts[:, 1]
        return out

    def rx(pts: np.ndarray, deg: float) -> np.ndarray:
        rad = math.radians(deg)
        if abs(rad) <= 1e-12:
            return pts
        out = pts.copy()
        c, s = math.cos(rad), math.sin(rad)
        out[:, 1] = c * pts[:, 1] - s * pts[:, 2]
        out[:, 2] = s * pts[:, 1] + c * pts[:, 2]
        return out

    def ry(pts: np.ndarray, deg: float) -> np.ndarray:
        rad = math.radians(deg)
        if abs(rad) <= 1e-12:
            return pts
        out = pts.copy()
        c, s = math.cos(rad), math.sin(rad)
        out[:, 0] =  c * pts[:, 0] + s * pts[:, 2]
        out[:, 2] = -s * pts[:, 0] + c * pts[:, 2]
        return out

    scale = np.asarray(camera_data["model_static"]["scale"], dtype=np.float64)
    base_z_rad = math.radians(base_rotate_z_deg)

    if transform_order == "blender_rig":
        if recenter_to_bbox_center:
            v -= bbox_center
        v *= scale
        v = rx(v, extra_rotate_x_deg)
        v = ry(v, extra_rotate_y_deg)
        v = rz(v, base_z_rad)
        v = rz(v, rotation_z_rad)
    elif transform_order == "eval":
        v = rz(v, base_z_rad)
        if recenter_to_bbox_center:
            v -= bbox_center
        v *= scale
        v = rz(v, rotation_z_rad)
        v = rx(v, extra_rotate_x_deg)
        v = ry(v, extra_rotate_y_deg)
    else:
        raise ValueError(f"Unknown transform_order: {transform_order}")

    v += np.asarray(camera_data["model_static"]["location"], dtype=np.float64)
    return v


# ── ray casting ───────────────────────────────────────────────────────────────

def get_view_matrix(camera_data: dict) -> np.ndarray:
    """Return 4×4 view matrix.

    If the JSON contains 'view_matrix' (MeshMamba/3DVA style), use it directly.
    Otherwise reconstruct from 'rotation_euler_radians' + 'location' (SAL3D style).
    """
    cam = camera_data["camera_static"]
    if "view_matrix" in cam:
        return np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)

    # Reconstruct from Blender XYZ Euler rotation + location
    rx, ry, rz = [float(a) for a in cam["rotation_euler_radians"]]

    def Rx(a: float) -> np.ndarray:
        return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])

    def Ry(a: float) -> np.ndarray:
        return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])

    def Rz(a: float) -> np.ndarray:
        return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])

    R = Rz(rz) @ Ry(ry) @ Rx(rx)  # Blender XYZ Euler order
    loc = np.array([float(x) for x in cam["location"]])

    cam_world = np.eye(4)
    cam_world[:3, :3] = R
    cam_world[:3, 3] = loc
    return np.linalg.inv(cam_world)


def screen_to_rays(
    camera_data: dict, x_norm: np.ndarray, y_norm: np.ndarray, proj_mat: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    ndc_x = x_norm * 2.0 - 1.0
    ndc_y = -(y_norm * 2.0 - 1.0)
    ones  = np.ones_like(ndc_x)
    ndc_near = np.stack([ndc_x, ndc_y, -ones, ones], axis=1)
    ndc_far  = np.stack([ndc_x, ndc_y,  ones, ones], axis=1)

    view_matrix = get_view_matrix(camera_data)
    inv_proj = np.linalg.inv(proj_mat)
    inv_view = np.linalg.inv(view_matrix)

    cam_near = (inv_proj @ ndc_near.T).T;  cam_near /= cam_near[:, 3:4]
    cam_far  = (inv_proj @ ndc_far.T).T;   cam_far  /= cam_far[:, 3:4]

    world_near = (inv_view @ cam_near.T).T
    world_far  = (inv_view @ cam_far.T).T

    origins    = world_near[:, :3]
    directions = world_far[:, :3] - world_near[:, :3]
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    return origins, directions


# ── metrics ───────────────────────────────────────────────────────────────────

def _normalize_sum(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    t = float(v.sum())
    return v / t if t > 0 and np.isfinite(t) else np.zeros_like(v)


def _normalize_minmax(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    lo, hi = float(v.min()), float(v.max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
        return np.zeros_like(v)
    return (v - lo) / (hi - lo)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b)) / d if d != 0.0 else 0.0


def _nss(pred: np.ndarray, mask: np.ndarray) -> float:
    pred = np.asarray(pred, dtype=np.float64)
    mask = np.asarray(mask, dtype=bool)
    if mask.sum() == 0:
        return 0.0
    std = float(pred.std())
    if std == 0.0:
        return 0.0
    return float(((pred - pred.mean()) / std)[mask].mean())


def _auc_judd(pred: np.ndarray, mask: np.ndarray) -> float:
    pred = _normalize_minmax(pred).reshape(-1)
    mask = np.asarray(mask, dtype=bool).reshape(-1)
    n_pos, n_neg = int(mask.sum()), int((~mask).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    thresholds = np.sort(np.unique(pred[mask]))[::-1]
    tp, fp = [0.0], [0.0]
    for thr in thresholds:
        above = pred >= thr
        tp.append(float(np.logical_and(above,  mask).sum()) / n_pos)
        fp.append(float(np.logical_and(above, ~mask).sum()) / n_neg)
    tp.append(1.0); fp.append(1.0)
    return float(np.trapezoid(np.asarray(tp), np.asarray(fp)))


def compute_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    proxy_percentiles: tuple[float, ...] = (90.0, 95.0, 99.0),
) -> dict[str, float]:
    pred = np.asarray(pred, dtype=np.float64).reshape(-1)
    gt   = np.asarray(gt,   dtype=np.float64).reshape(-1)

    lcc, _  = pearsonr(pred, gt)
    spr, _  = spearmanr(pred, gt)

    pred_prob = _normalize_sum(np.clip(pred, 0, None))
    gt_prob   = _normalize_sum(np.clip(gt,   0, None))
    pred_unit = _normalize_minmax(pred)
    gt_unit   = _normalize_minmax(gt)
    eps = 1e-12

    m = {
        "CC":      float(lcc),
        "LCC":     float(lcc),
        "SIM":     float(np.minimum(pred_prob, gt_prob).sum()),
        "KLD":     float(np.sum((gt_prob + eps) * np.log((gt_prob + eps) / (pred_prob + eps)))),
        "MSE":     float(np.mean((pred_unit - gt_unit) ** 2)),
        "MAE":     float(np.mean(np.abs(pred_unit - gt_unit))),
        "Spearman": float(spr),
        "Cosine":  _cosine(pred, gt),
        "PredictionSum":  float(pred.sum()),
        "GroundTruthSum": float(gt.sum()),
    }
    for pct in proxy_percentiles:
        thr  = float(np.quantile(gt_unit, pct / 100.0))
        mask = gt_unit >= thr
        top  = 100.0 - pct
        lbl  = str(int(round(top))) if math.isclose(top, round(top)) else str(top).replace(".", "p")
        m[f"NSS_gt_top_{lbl}pct_proxy"]       = _nss(pred_unit, mask)
        m[f"AUC_Judd_gt_top_{lbl}pct_proxy"]  = _auc_judd(pred_unit, mask)
        m[f"GTMaskCount_top_{lbl}pct_proxy"]  = float(mask.sum())
    return m


# ── main evaluation loop ──────────────────────────────────────────────────────

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
    projection_fov_mode: str,
    transform_order: str,
) -> tuple[np.ndarray, np.ndarray, dict]:
    n_verts = len(mesh.vertices)
    raycast_counts = np.zeros(n_verts, dtype=np.float64)
    cone_counts    = np.zeros(n_verts, dtype=np.float64)

    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]
    frames_list = camera_data["frames"]

    proj_mat, proj_info = resolve_projection_matrix(
        camera_data, override_fov_deg, projection_fov_mode
    )

    total_points = total_hits = total_cone_v = 0

    for frame, batch in gaze_batches.items():
        if batch.x_norm.size == 0:
            continue
        if frame >= len(frames_list):
            continue
        rot_z = float(frames_list[frame]["rotation_z_radians"])

        xmesh = mesh.copy()
        xmesh.vertices = apply_model_transform(
            mesh.vertices, camera_data, rot_z,
            recenter_to_bbox_center, base_rotate_z_deg,
            extra_rotate_x_deg, extra_rotate_y_deg, transform_order,
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
        tri_verts  = xmesh.faces[tri_idx]
        tri_coords = xmesh.vertices[tri_verts]
        dists_lv   = np.linalg.norm(tri_coords - hit_pts[:, None, :], axis=2)
        nearest_v  = tri_verts[np.arange(len(tri_verts)), np.argmin(dists_lv, axis=1)]
        np.add.at(raycast_counts, nearest_v, 1.0)

        # cone_gaussian_on_mesh
        vtree = cKDTree(xmesh.vertices)
        depth = np.linalg.norm(hit_pts - origins[ray_idx], axis=1)
        sigma_world = np.maximum(depth * math.tan(math.radians(sigma_deg)), 1e-6)
        for pt, sigma in zip(hit_pts, sigma_world):
            idxs = vtree.query_ball_point(pt, r=radius_sigma_mult * sigma) or [int(vtree.query(pt)[1])]
            lv   = xmesh.vertices[np.asarray(idxs, dtype=np.int64)]
            w    = np.exp(-0.5 * np.sum((lv - pt) ** 2, axis=1) / sigma ** 2)
            cone_counts[np.asarray(idxs, dtype=np.int64)] += w
            total_cone_v += len(idxs)

        total_hits += len(hit_pts)

    stats = {
        "total_gaze_points":        total_points,
        "successful_hits":          total_hits,
        "hit_rate":                 total_hits / total_points if total_points else 0.0,
        "raycast_nonzero_vertices": int(np.count_nonzero(raycast_counts)),
        "cone_nonzero_vertices":    int(np.count_nonzero(cone_counts)),
        "projection":               proj_info,
    }
    return raycast_counts, cone_counts, stats


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args  = parse_args()
    paths = resolve_model_paths(args)
    ensure_exists(paths)

    with paths["json"].open("r", encoding="utf-8") as fh:
        camera_data = json.load(fh)

    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected a single Trimesh, got {type(mesh)}")

    gaze_batches, gaze_stats = load_gaze_batches(
        paths["csv"],
        fps=int(camera_data["video_info"]["fps"]),
        total_frames=int(camera_data["video_info"]["total_frames"]),
    )

    # GT: load and align to OBJ vertex order
    gt = load_gt_aligned_to_obj(paths["gt"], np.asarray(mesh.vertices), args.gt_column)
    gt_col_name = "smooth_saliency" if args.gt_column == 6 else "binary_saliency"

    # Tag
    tag_parts = [f"rotx{args.extra_rotate_x_deg}".replace(".", "p")] if abs(args.extra_rotate_x_deg) > 1e-12 else []
    if args.recenter_to_bbox_center:
        tag_parts.append("recenter")
    if args.projection_fov_mode != "vertical":
        tag_parts.append(args.projection_fov_mode.replace("_", ""))
    if args.transform_order != "eval":
        tag_parts.append(args.transform_order)
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
        projection_fov_mode=args.projection_fov_mode,
        transform_order=args.transform_order,
    )

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_raycast_vertices.txt", raycast, fmt="%.10f")
    np.savetxt(out_dir / f"{args.model}_cone_vertices.txt",    cone,    fmt="%.10f")

    results = {
        "raycast_nearest_vertex": compute_metrics(raycast, gt),
        "cone_gaussian_on_mesh":  compute_metrics(cone,    gt),
    }

    report = {
        "model":      args.model,
        "tag":        tag,
        "dataset":    "SAL3D",
        "gt_file":    str(paths["gt"].name),
        "gt_column":  args.gt_column,
        "gt_type":    gt_col_name,
        "n_vertices": int(len(mesh.vertices)),
        "gaze_stats": gaze_stats,
        "run_stats":  run_stats,
        "method_params": {
            "sigma_deg":               args.sigma_deg,
            "radius_sigma_mult":       args.radius_sigma_mult,
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg":       args.base_rotate_z_deg,
            "extra_rotate_x_deg":      args.extra_rotate_x_deg,
            "extra_rotate_y_deg":      args.extra_rotate_y_deg,
            "override_fov_deg":        args.override_fov_deg,
            "projection_fov_mode":     args.projection_fov_mode,
            **run_stats["projection"],
            "transform_order":         args.transform_order,
        },
        "metrics_vs_gt": results,
    }

    report_path = out_dir / f"{args.model}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()

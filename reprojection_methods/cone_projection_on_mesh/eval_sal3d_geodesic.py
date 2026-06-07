#!/usr/bin/env python3
"""
Evaluate geodesic_diffusion_on_mesh on one SAL3D model.

Method pipeline:
  1. Raycast each gaze point → hit triangle → nearest vertex (cone Gaussian at vertex level).
  2. Build a mesh Laplacian weighted by inverse edge length.
  3. Apply heat diffusion: signal = expm_multiply(-t * L, vertex_signal)
     where t = (sigma_mesh)^2 / 2.
  4. Compare diffused per-vertex signal against per-vertex GT (Gaze/*.txt).

Sigma parameters:
  --sigma-visual-deg 1.0   visual-angle sigma of the receptive field
  --vertex-angle-deg 0.1   approximate vertex spacing in visual angle
  sigma_steps = sigma_visual_deg / vertex_angle_deg   (default = 10 vertex spacings)
  sigma_mesh  = sigma_steps * mean_edge_length
  t           = sigma_mesh^2 / 2

GT granularity: per-vertex (Gaze/<model>.txt, rows × 8 cols, col 6 = fixation_density).
Two metric sections:
  metrics_vs_gt_full_mesh    — all OBJ vertices
  metrics_vs_gt_covered_only — only GT-covered vertices (valid for ALL models)

Transform recipe (validated, Blender IoU ≥ 0.977 across all 57 SAL3D models):
  --recenter-to-bbox-center --extra-rotate-x-deg 90.0
  --projection-fov-mode horizontal_to_vertical
  --transform-order blender_rig

Env vars:
  SAL3D_DATASET_ROOT    — root containing Gaze/, Meshes/
  SAL3D_CSV_ROOT        — per-model CSV gaze files (our participants)
  SAL3D_JSON_ROOT       — per-model Sal3D_<model>.json files
  SAL3D_OUTPUT_DIR      — output directory
  SAL3D_SMOOTH_GAZE_DIR — directory with <model>_neighbors.txt for GT smoothing
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
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import expm_multiply
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
        description="Evaluate geodesic_diffusion_on_mesh on one SAL3D model."
    )
    parser.add_argument("--model", default="bunny")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("SAL3D_DATASET_ROOT", "e.g. /srv/datasets/SAL3D/SAL3D_Dataset"),
    )
    parser.add_argument(
        "--csv-root",
        type=Path,
        default=_env_path("SAL3D_CSV_ROOT", "e.g. /srv/side_inputs/SAL3D/csv"),
    )
    parser.add_argument(
        "--json-root",
        type=Path,
        default=_env_path("SAL3D_JSON_ROOT", "e.g. /srv/side_inputs/SAL3D/json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_env_path(
            "SAL3D_OUTPUT_DIR",
            str(REPO_ROOT / "results" / "sal3d" / "geodesic_diffusion"),
        ),
    )
    parser.add_argument("--gt-column", type=int, default=6, choices=[6, 7])
    parser.add_argument(
        "--smooth-gaze-dir",
        type=Path,
        default=_env_path("SAL3D_SMOOTH_GAZE_DIR", ""),
    )
    parser.add_argument("--smooth-ratio", type=int, default=500)
    # Cone projection params
    parser.add_argument("--sigma-deg", type=float, default=1.0)
    parser.add_argument("--radius-sigma-mult", type=float, default=3.0)
    # Geodesic diffusion params
    parser.add_argument("--sigma-visual-deg", type=float, default=1.0,
                        help="Visual-angle sigma for heat diffusion (paper default 1.0°).")
    parser.add_argument("--vertex-angle-deg", type=float, default=0.1,
                        help="Approximate vertex spacing in visual angle (paper default 0.1°).")
    # Transform params
    parser.add_argument("--recenter-to-bbox-center",
                        action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--base-rotate-z-deg", type=float, default=0.0)
    parser.add_argument("--extra-rotate-x-deg", type=float, default=90.0)
    parser.add_argument("--extra-rotate-y-deg", type=float, default=0.0)
    parser.add_argument("--override-fov-deg", type=float, default=None)
    parser.add_argument(
        "--projection-fov-mode",
        choices=["vertical", "horizontal_to_vertical", "json"],
        default="horizontal_to_vertical",
    )
    parser.add_argument(
        "--transform-order",
        choices=["eval", "blender_rig"],
        default="blender_rig",
    )
    parser.add_argument("--tag", default=None)
    return parser.parse_args()


# ── path resolution (from eval_sal3d_cone.py) ────────────────────────────────

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
    return {p.name.lower(): p for p in sorted(directory.glob(f"*{suffix}")) if p.is_file()}


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
        raise FileNotFoundError(f"OBJ not found for '{args.model}' in {args.dataset_root / 'Meshes'}")
    gt_path = _resolve(args.dataset_root / "Gaze", names, ".txt")
    if gt_path is None:
        raise FileNotFoundError(f"GT not found for '{args.model}' in {args.dataset_root / 'Gaze'}")
    csv_path = _resolve(args.csv_root, names, ".csv")
    if csv_path is None:
        raise FileNotFoundError(f"CSV not found for '{args.model}' in {args.csv_root}")
    json_names = [f"Sal3D_{n}" for n in names]
    json_path = _resolve(args.json_root, json_names, ".json")
    if json_path is None:
        raise FileNotFoundError(f"JSON not found for '{args.model}' (Sal3D_) in {args.json_root}")
    return {"obj": obj_path, "gt": gt_path, "csv": csv_path, "json": json_path}


def ensure_exists(paths: dict[str, Path]) -> None:
    missing = [f"{k}: {v}" for k, v in paths.items() if not v.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))


# ── Smooth Gaze + GT loading (from eval_sal3d_cone.py) ───────────────────────

def load_smooth_gaze(smooth_gaze_dir: Path, model: str) -> dict[int, list[int]] | None:
    if not smooth_gaze_dir or not Path(smooth_gaze_dir).is_dir():
        return None
    for name in _candidate_model_names(model):
        path = Path(smooth_gaze_dir) / f"{name}_neighbors.txt"
        if path.exists():
            break
    else:
        return None
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    ids: list[int] = [int(lines[0].replace(" neighbors", "").strip())]
    neighbor_lists: list[list[int]] = []
    for line in lines[1:]:
        parts = line.strip().split(";")
        if "neighbors" in line:
            neighbor_lists.append([int(x) for x in parts[:-1]])
            ids.append(int(parts[-1].replace(" neighbors", "").strip()))
        else:
            neighbor_lists.append([int(x) for x in parts if x])
    return {vid: nbrs for vid, nbrs in zip(ids, neighbor_lists)}


def apply_gt_smoothing(raw_gt: np.ndarray, smooth_gaze: dict[int, list[int]],
                       ratio: int = 500) -> np.ndarray:
    smoothed = raw_gt.copy()
    for vid, nbrs in smooth_gaze.items():
        v = float(raw_gt[vid])
        if v == 0.0:
            continue
        nbrs_clipped = nbrs[:ratio]
        if not nbrs_clipped:
            continue
        r = np.linspace(0.9 * v, 0.0, len(nbrs_clipped))
        for k, nb in enumerate(nbrs_clipped):
            smoothed[nb] += r[k]
    return smoothed


def load_gt_aligned_to_obj(
    gaze_txt: Path, mesh_vertices: np.ndarray,
    gt_column: int, smooth_gaze: dict | None = None, smooth_ratio: int = 500,
) -> tuple[np.ndarray, np.ndarray, bool]:
    data = np.loadtxt(gaze_txt)
    gaze_xyz = data[:, :3]
    raw_sal  = data[:, gt_column].astype(np.float64)
    n_verts, n_gaze = len(mesh_vertices), len(gaze_xyz)
    if n_gaze > n_verts:
        raise ValueError(f"GT rows ({n_gaze}) > OBJ vertices ({n_verts})")
    if smooth_gaze is not None and gt_column != 7:
        gaze_sal = apply_gt_smoothing(raw_sal, smooth_gaze, ratio=smooth_ratio)
        smoothed = True
    else:
        gaze_sal = raw_sal
        smoothed = False
    tree = cKDTree(mesh_vertices)
    dists, idxs = tree.query(gaze_xyz, k=1)
    if dists.max() > 1e-4:
        raise ValueError(f"GT vertex mismatch: max dist={dists.max():.6f}")
    gt = np.zeros(n_verts, dtype=np.float64)
    gt[idxs] = gaze_sal
    gt_mask = np.zeros(n_verts, dtype=bool)
    gt_mask[idxs] = True
    return gt, gt_mask, smoothed


# ── gaze loading ──────────────────────────────────────────────────────────────

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
    return batches, {
        "num_rows": int(len(df)),
        "num_participants": int(df["participation_id"].nunique()),
        "num_points": int(total_points),
        "num_frames_with_points": int(len(batches)),
    }


# ── view / projection (from eval_sal3d_cone.py) ──────────────────────────────

def get_view_matrix(camera_data: dict) -> np.ndarray:
    cam = camera_data["camera_static"]
    if "view_matrix" in cam:
        return np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)
    rx_a, ry_a, rz_a = [float(a) for a in cam["rotation_euler_radians"]]
    def Rx(a): return np.array([[1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
    def Ry(a): return np.array([[math.cos(a),0,math.sin(a)],[0,1,0],[-math.sin(a),0,math.cos(a)]])
    def Rz(a): return np.array([[math.cos(a),-math.sin(a),0],[math.sin(a),math.cos(a),0],[0,0,1]])
    R = Rz(rz_a) @ Ry(ry_a) @ Rx(rx_a)
    loc = np.array([float(x) for x in cam["location"]])
    cam_world = np.eye(4)
    cam_world[:3, :3] = R
    cam_world[:3, 3] = loc
    return np.linalg.inv(cam_world)


def build_projection_matrix_from_fov(fov_deg, aspect_ratio, clip_start, clip_end):
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    near, far = float(clip_start), float(clip_end)
    return np.array([[f/aspect_ratio,0,0,0],[0,f,0,0],
                     [0,0,-(far+near)/(far-near),-(2*far*near)/(far-near)],[0,0,-1,0]], dtype=np.float64)


def resolve_projection_matrix(camera_data, override_fov_deg, mode):
    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]
    if mode == "horizontal_to_vertical":
        h_fov = float(override_fov_deg) if override_fov_deg is not None else (
            float(cam["fov_degrees"]) if "fov_degrees" in cam else math.degrees(float(cam["fov_radians"])))
        src = "override_fov_deg" if override_fov_deg is not None else "json_fov"
        eff = math.degrees(2.0 * math.atan(math.tan(math.radians(h_fov) * 0.5) / float(vi["aspect_ratio"])))
        return build_projection_matrix_from_fov(eff, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]), {
            "projection_fov_mode": "horizontal_to_vertical", "input_fov_deg": h_fov,
            "effective_vertical_fov_deg": eff, "fov_source": src}
    if mode == "vertical":
        if override_fov_deg is None:
            return np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4), {
                "projection_fov_mode": "vertical", "input_fov_deg": None, "effective_vertical_fov_deg": None}
        eff = float(override_fov_deg)
        return build_projection_matrix_from_fov(eff, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]), {
            "projection_fov_mode": "vertical", "input_fov_deg": eff, "effective_vertical_fov_deg": eff}
    return np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4), {
        "projection_fov_mode": "json", "input_fov_deg": None, "effective_vertical_fov_deg": None}


def apply_model_transform(vertices, camera_data, rotation_z_rad,
                          recenter_to_bbox_center, base_rotate_z_deg,
                          extra_rotate_x_deg, extra_rotate_y_deg, transform_order):
    v = np.asarray(vertices, dtype=np.float64).copy()
    bbox_center = 0.5 * (v.min(axis=0) + v.max(axis=0))

    def rz(pts, rad):
        if abs(rad) <= 1e-12: return pts
        out = pts.copy(); c, s = math.cos(rad), math.sin(rad)
        out[:, 0] = c * pts[:, 0] - s * pts[:, 1]
        out[:, 1] = s * pts[:, 0] + c * pts[:, 1]
        return out

    def rx(pts, deg):
        rad = math.radians(deg)
        if abs(rad) <= 1e-12: return pts
        out = pts.copy(); c, s = math.cos(rad), math.sin(rad)
        out[:, 1] = c * pts[:, 1] - s * pts[:, 2]
        out[:, 2] = s * pts[:, 1] + c * pts[:, 2]
        return out

    def ry(pts, deg):
        rad = math.radians(deg)
        if abs(rad) <= 1e-12: return pts
        out = pts.copy(); c, s = math.cos(rad), math.sin(rad)
        out[:, 0] =  c * pts[:, 0] + s * pts[:, 2]
        out[:, 2] = -s * pts[:, 0] + c * pts[:, 2]
        return out

    scale = np.asarray(camera_data["model_static"]["scale"], dtype=np.float64)
    base_z_rad = math.radians(base_rotate_z_deg)
    if transform_order == "blender_rig":
        if recenter_to_bbox_center: v -= bbox_center
        v *= scale
        v = rx(v, extra_rotate_x_deg); v = ry(v, extra_rotate_y_deg)
        v = rz(v, base_z_rad); v = rz(v, rotation_z_rad)
    elif transform_order == "eval":
        v = rz(v, base_z_rad)
        if recenter_to_bbox_center: v -= bbox_center
        v *= scale; v = rz(v, rotation_z_rad)
        v = rx(v, extra_rotate_x_deg); v = ry(v, extra_rotate_y_deg)
    else:
        raise ValueError(f"Unknown transform_order: {transform_order}")
    v += np.asarray(camera_data["model_static"]["location"], dtype=np.float64)
    return v


def screen_to_rays(camera_data, x_norm, y_norm, proj_mat):
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


# ── geodesic diffusion ────────────────────────────────────────────────────────

def build_weighted_laplacian(vertices: np.ndarray, faces: np.ndarray):
    edge_pairs: set[tuple[int, int]] = set()
    for tri in faces:
        a, b, c = int(tri[0]), int(tri[1]), int(tri[2])
        for u, v in ((a, b), (b, c), (c, a)):
            if u > v: u, v = v, u
            edge_pairs.add((u, v))
    rows, cols, weights, lengths = [], [], [], []
    for u, v in edge_pairs:
        length = float(np.linalg.norm(vertices[u] - vertices[v]))
        if length == 0.0: continue
        w = 1.0 / length
        rows.extend([u, v]); cols.extend([v, u])
        weights.extend([w, w]); lengths.append(length)
    n = len(vertices)
    W = coo_matrix((weights, (rows, cols)), shape=(n, n)).tocsr()
    degree = np.asarray(W.sum(axis=1)).ravel()
    L = diags(degree) - W
    mean_edge = float(np.mean(lengths)) if lengths else 1.0
    return L, mean_edge


def apply_geodesic_diffusion(vertex_signal, laplacian, sigma_visual_deg, vertex_angle_deg, mean_edge):
    sigma_steps = sigma_visual_deg / vertex_angle_deg
    sigma_mesh  = sigma_steps * mean_edge
    t = (sigma_mesh ** 2) / 2.0
    diffused = expm_multiply((-t) * laplacian, vertex_signal.astype(np.float64))
    diffused = np.maximum(diffused, 0.0)
    if diffused.sum() > 0.0 and vertex_signal.sum() > 0.0:
        diffused *= vertex_signal.sum() / diffused.sum()
    return diffused, {
        "sigma_visual_deg": sigma_visual_deg,
        "vertex_angle_deg": vertex_angle_deg,
        "sigma_vertex_steps": sigma_steps,
        "sigma_mesh_units": sigma_mesh,
        "heat_time_t": t,
        "mean_edge_length": mean_edge,
    }


# ── metrics (from eval_sal3d_cone.py) ────────────────────────────────────────

def _normalize_sum(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    t = float(v.sum())
    return v / t if t > 0 and np.isfinite(t) else np.zeros_like(v)


def _normalize_minmax(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    lo, hi = float(v.min()), float(v.max())
    if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo: return np.zeros_like(v)
    return (v - lo) / (hi - lo)


def _cosine(a, b):
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b)) / d if d != 0.0 else 0.0


def _nss(pred, mask):
    pred = np.asarray(pred, dtype=np.float64); mask = np.asarray(mask, dtype=bool)
    if not mask.any(): return 0.0
    std = float(pred.std())
    if std == 0.0: return 0.0
    return float(((pred - pred.mean()) / std)[mask].mean())


def _auc_judd(pred, mask):
    pred = _normalize_minmax(pred).reshape(-1); mask = np.asarray(mask, dtype=bool).reshape(-1)
    n_pos, n_neg = int(mask.sum()), int((~mask).sum())
    if n_pos == 0 or n_neg == 0: return 0.5
    thresholds = np.sort(np.unique(pred[mask]))[::-1]
    tp, fp = [0.0], [0.0]
    for thr in thresholds:
        above = pred >= thr
        tp.append(float(np.logical_and(above, mask).sum()) / n_pos)
        fp.append(float(np.logical_and(above, ~mask).sum()) / n_neg)
    tp.append(1.0); fp.append(1.0)
    return float(np.trapezoid(np.asarray(tp), np.asarray(fp)))


def compute_metrics(pred, gt, proxy_percentiles=(90.0, 95.0, 99.0)):
    pred = np.asarray(pred, dtype=np.float64).reshape(-1)
    gt   = np.asarray(gt,   dtype=np.float64).reshape(-1)
    lcc, _ = pearsonr(pred, gt); spr, _ = spearmanr(pred, gt)
    pred_prob = _normalize_sum(np.clip(pred, 0, None))
    gt_prob   = _normalize_sum(np.clip(gt,   0, None))
    pred_unit = _normalize_minmax(pred); gt_unit = _normalize_minmax(gt)
    eps = 1e-12
    m = {
        "CC": float(lcc), "LCC": float(lcc),
        "SIM": float(np.minimum(pred_prob, gt_prob).sum()),
        "KLD": float(np.sum((gt_prob+eps) * np.log((gt_prob+eps)/(pred_prob+eps)))),
        "MSE": float(np.mean((pred_unit - gt_unit)**2)),
        "MAE": float(np.mean(np.abs(pred_unit - gt_unit))),
        "Spearman": float(spr), "Cosine": _cosine(pred, gt),
        "PredictionSum": float(pred.sum()), "GroundTruthSum": float(gt.sum()),
    }
    for pct in proxy_percentiles:
        thr = float(np.quantile(gt_unit, pct / 100.0))
        mask = gt_unit >= thr
        top = 100.0 - pct
        lbl = str(int(round(top))) if math.isclose(top, round(top)) else str(top).replace(".", "p")
        m[f"NSS_gt_top_{lbl}pct_proxy"]      = _nss(pred_unit, mask)
        m[f"AUC_Judd_gt_top_{lbl}pct_proxy"] = _auc_judd(pred_unit, mask)
        m[f"GTMaskCount_top_{lbl}pct_proxy"] = float(mask.sum())
    return m


# ── main evaluation loop ──────────────────────────────────────────────────────

def run_geodesic(
    mesh: trimesh.Trimesh,
    camera_data: dict,
    gaze_batches: dict[int, FrameGazeBatch],
    sigma_deg: float,
    radius_sigma_mult: float,
    sigma_visual_deg: float,
    vertex_angle_deg: float,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    override_fov_deg: float | None,
    projection_fov_mode: str,
    transform_order: str,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Returns:
        vert_geodesic : (N_vertices,) diffused saliency
        vert_cone     : (N_vertices,) pre-diffusion cone saliency (baseline)
        stats         : run statistics dict
    """
    n_verts = len(mesh.vertices)
    vert_cone = np.zeros(n_verts, dtype=np.float64)

    frames_list = camera_data["frames"]
    proj_mat, proj_info = resolve_projection_matrix(camera_data, override_fov_deg, projection_fov_mode)

    total_points = total_hits = 0

    for frame, batch in gaze_batches.items():
        if batch.x_norm.size == 0 or frame >= len(frames_list):
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

        hit_pts     = np.asarray(locs,    dtype=np.float64)
        ray_idx     = np.asarray(idx_ray, dtype=np.int64)

        vtree = cKDTree(xmesh.vertices)
        origins_at_hit = origins[ray_idx]
        depth = np.linalg.norm(hit_pts - origins_at_hit, axis=1)
        sigma_world = np.maximum(depth * math.tan(math.radians(sigma_deg)), 1e-6)
        for pt, sigma in zip(hit_pts, sigma_world):
            idxs = vtree.query_ball_point(pt, r=radius_sigma_mult * sigma) or [int(vtree.query(pt)[1])]
            lv = xmesh.vertices[np.asarray(idxs, dtype=np.int64)]
            w  = np.exp(-0.5 * np.sum((lv - pt)**2, axis=1) / sigma**2)
            vert_cone[np.asarray(idxs, dtype=np.int64)] += w

        total_hits += len(hit_pts)

    # Build Laplacian on SCALED vertices (world-space units).
    # Apply only the uniform scale from the Blender rig — no rotation, no translation.
    # This ensures sigma_mesh / mean_edge are in world-space metres, not OBJ-space units.
    scale = np.asarray(camera_data["model_static"]["scale"], dtype=np.float64)
    scaled_verts = np.asarray(mesh.vertices, dtype=np.float64) * scale
    laplacian, mean_edge = build_weighted_laplacian(
        scaled_verts,
        np.asarray(mesh.faces, dtype=np.int32),
    )

    vert_geodesic, diffusion_info = apply_geodesic_diffusion(
        vert_cone, laplacian, sigma_visual_deg, vertex_angle_deg, mean_edge
    )

    stats = {
        "total_gaze_points":         total_points,
        "successful_hits":           total_hits,
        "hit_rate":                  total_hits / total_points if total_points else 0.0,
        "cone_nonzero_vertices":     int(np.count_nonzero(vert_cone)),
        "geodesic_nonzero_vertices": int(np.count_nonzero(vert_geodesic)),
        "projection":                proj_info,
        "diffusion":                 diffusion_info,
    }
    return vert_geodesic, vert_cone, stats


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

    # Load Smooth Gaze for GT densification
    smooth_gaze_data = None
    smooth_gaze_path_used = None
    sg_dir = args.smooth_gaze_dir
    if sg_dir and Path(str(sg_dir)).is_dir():
        smooth_gaze_data = load_smooth_gaze(Path(str(sg_dir)), args.model)
        if smooth_gaze_data is not None:
            smooth_gaze_path_used = str(sg_dir)

    gt, gt_mask, gt_was_smoothed = load_gt_aligned_to_obj(
        paths["gt"], np.asarray(mesh.vertices),
        args.gt_column, smooth_gaze=smooth_gaze_data, smooth_ratio=args.smooth_ratio,
    )
    gt_col_name = ("fixation_density" if args.gt_column == 6 else "binary_fixation") + \
                  ("_smoothed" if gt_was_smoothed else "")

    n_verts      = len(mesh.vertices)
    n_gt_covered = int(gt_mask.sum())
    gt_coverage  = n_gt_covered / n_verts if n_verts > 0 else 0.0
    match_type   = "direct" if n_gt_covered == n_verts else "subset"

    tag_parts = []
    if args.recenter_to_bbox_center:           tag_parts.append("recenter")
    if abs(args.extra_rotate_x_deg) > 1e-12:   tag_parts.append(f"rotx{args.extra_rotate_x_deg}".replace(".", "p"))
    if args.projection_fov_mode != "vertical":  tag_parts.append(args.projection_fov_mode.replace("_", ""))
    if args.transform_order != "eval":          tag_parts.append(args.transform_order)
    tag_parts.append(f"geodiff_sigma{args.sigma_visual_deg}".replace(".", "p"))
    if gt_was_smoothed:                         tag_parts.append("gt_smoothed")
    tag = args.tag or "_".join(tag_parts)

    vert_geodesic, vert_cone, run_stats = run_geodesic(
        mesh=mesh, camera_data=camera_data, gaze_batches=gaze_batches,
        sigma_deg=args.sigma_deg, radius_sigma_mult=args.radius_sigma_mult,
        sigma_visual_deg=args.sigma_visual_deg, vertex_angle_deg=args.vertex_angle_deg,
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
    np.savetxt(out_dir / f"{args.model}_geodesic_vertices.txt", vert_geodesic, fmt="%.10f")
    np.savetxt(out_dir / f"{args.model}_cone_baseline_vertices.txt", vert_cone, fmt="%.10f")

    def metrics_pair(pred):
        return {
            "geodesic_diffusion_on_mesh": compute_metrics(pred, gt),
            "cone_vertex_baseline":       compute_metrics(vert_cone, gt),
        }

    def metrics_pair_masked(pred):
        return {
            "geodesic_diffusion_on_mesh": compute_metrics(pred[gt_mask], gt[gt_mask]),
            "cone_vertex_baseline":       compute_metrics(vert_cone[gt_mask], gt[gt_mask]),
        }

    report = {
        "model":      args.model,
        "tag":        tag,
        "dataset":    "SAL3D",
        "gt_file":    str(paths["gt"].name),
        "gt_column":  args.gt_column,
        "gt_type":    gt_col_name,
        "gt_smoothed":          gt_was_smoothed,
        "gt_smooth_gaze_dir":   smooth_gaze_path_used,
        "gt_smooth_ratio":      args.smooth_ratio if gt_was_smoothed else None,
        "gt_smooth_fixated_verts": len(smooth_gaze_data) if smooth_gaze_data else None,
        "n_vertices":      n_verts,
        "n_gt_covered":    n_gt_covered,
        "gt_coverage_pct": round(gt_coverage * 100.0, 2),
        "gt_match_type":   match_type,
        "gaze_stats":  gaze_stats,
        "run_stats":   run_stats,
        "method_params": {
            "sigma_deg":               args.sigma_deg,
            "radius_sigma_mult":       args.radius_sigma_mult,
            "sigma_visual_deg":        args.sigma_visual_deg,
            "vertex_angle_deg":        args.vertex_angle_deg,
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "extra_rotate_x_deg":      args.extra_rotate_x_deg,
            "projection_fov_mode":     args.projection_fov_mode,
            "transform_order":         args.transform_order,
            **run_stats["projection"],
            **run_stats["diffusion"],
        },
        # Full-mesh metrics (valid only for direct-match 20K models)
        "metrics_vs_gt_full_mesh":    metrics_pair(vert_geodesic),
        # Covered-only metrics (valid for ALL models — use this for comparisons)
        "metrics_vs_gt_covered_only": metrics_pair_masked(vert_geodesic),
    }

    report_path = out_dir / f"{args.model}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()

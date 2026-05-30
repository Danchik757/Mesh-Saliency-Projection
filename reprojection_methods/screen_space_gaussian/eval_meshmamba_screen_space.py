#!/usr/bin/env python3
"""
Evaluate screen-space Gaussian saliency projection on one MeshMamba non_texture model.

Method (screen_space_gaussian):
  1. Accumulate all gaze points into a 2D density image (low-res, Gaussian-blurred).
  2. For each animation frame that has gaze data, transform face centroids to world
     space and project them to screen coordinates using the JSON camera matrices.
  3. Sample the gaze density image at each face centroid's screen position.
  4. Accumulate contributions weighted by the number of gaze points in that frame.
  5. Compare the resulting per-face saliency map against the per-face GT CSV.

GT granularity: per-face CSV (one float per line, N_faces lines).
JSON prefix:    MeshMamba_non_texture_<model>.json

Env vars (used when CLI args are not provided):
  MESHMAMBA_NON_TEXTURE_ROOT  — dataset root (MeshFile/non_texture, SaliencyMap/non_texture)
  MESHMAMBA_CSV_ROOT          — directory with per-model CSV gaze files
  MESHMAMBA_JSON_ROOT         — directory with per-model JSON camera/animation files
  MESHMAMBA_OUTPUT_DIR        — output directory
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
from scipy.ndimage import gaussian_filter
from scipy.stats import pearsonr, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Internal gaze density image resolution. Lower than 1920×1080 for speed; the
# Gaussian sigma is specified as a fraction of image width so it scales correctly.
_IMG_W = 256
_IMG_H = 144


@dataclass
class FrameGazeBatch:
    x_norm: np.ndarray
    y_norm: np.ndarray


def _env_path(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var, fallback))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate screen_space_gaussian on one MeshMamba non_texture model."
    )
    parser.add_argument("--model", default="Starfruit_L3", help="MeshMamba model name.")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("MESHMAMBA_NON_TEXTURE_ROOT", "e.g. /srv/datasets/MeshMamba_non_texture"),
        help="Dataset root containing MeshFile/non_texture and SaliencyMap/non_texture.",
    )
    parser.add_argument(
        "--csv-root",
        type=Path,
        default=_env_path("MESHMAMBA_CSV_ROOT", "e.g. /srv/side_inputs/MeshMamba_non_texture/csv"),
        help="Directory with per-model MeshMamba CSV gaze files.",
    )
    parser.add_argument(
        "--json-root",
        type=Path,
        default=_env_path("MESHMAMBA_JSON_ROOT", "e.g. /srv/side_inputs/MeshMamba_non_texture/json"),
        help="Directory with per-model MeshMamba JSON camera/animation files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_env_path(
            "MESHMAMBA_OUTPUT_DIR",
            str(REPO_ROOT / "results" / "meshmamba" / "screen_space_gaussian"),
        ),
        help="Output directory for saliency maps and the evaluation report.",
    )
    parser.add_argument(
        "--sigma-screen",
        type=float,
        default=0.05,
        help="Gaussian sigma as a fraction of image width (default 0.05 = 5%%).",
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


def find_gt_file(gt_dir: Path, model: str) -> Path:
    candidates = [
        gt_dir / f"{model}.csv",
        gt_dir / f"{model.replace('_', '-')}.csv",
        gt_dir / f"{model.replace('-', '_')}.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    model_norm = model.lower().replace("_", "-").replace(" ", "-")
    for f in sorted(gt_dir.glob("*.csv")):
        if f.stem.lower().replace("_", "-").replace(" ", "-") == model_norm:
            return f
    available = ", ".join(f.name for f in sorted(gt_dir.glob("*.csv")))
    raise FileNotFoundError(
        f"GT file not found for model '{model}' in {gt_dir}.\n"
        f"Tried: {', '.join(str(c.name) for c in candidates)}\n"
        f"Available: {available}"
    )


def find_obj_file(mesh_dir: Path, model: str) -> Path:
    model_dir = mesh_dir / model
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")
    candidates = [
        model_dir / f"{model}.obj",
        model_dir / f"{model.replace('_', '-')}.obj",
        model_dir / f"{model.replace('-', '_')}.obj",
    ]
    for c in candidates:
        if c.exists():
            return c
    objs = sorted(model_dir.glob("*.obj"))
    if objs:
        return objs[0]
    raise FileNotFoundError(f"No OBJ file found in {model_dir}")


def resolve_model_paths(args: argparse.Namespace) -> dict[str, Path]:
    mesh_dir = args.dataset_root / "MeshFile" / "non_texture"
    gt_dir   = args.dataset_root / "SaliencyMap" / "non_texture"
    obj_path = find_obj_file(mesh_dir, args.model)
    gt_path  = find_gt_file(gt_dir, args.model)
    return {
        "csv":  args.csv_root  / f"{args.model}.csv",
        "json": args.json_root / f"MeshMamba_non_texture_{args.model}.json",
        "obj":  obj_path,
        "gt":   gt_path,
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


def world_to_screen(
    points_w: np.ndarray,
    view_matrix: np.ndarray,
    proj_mat: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project world-space points to fractional screen coords [0,1]×[0,1].

    Returns (screen_xy, w_clip):
      screen_xy — (N, 2) array of (x_frac, y_frac); values outside [0,1] are off-screen.
      w_clip    — (N,) clip-space w values; negative means behind the camera.
    """
    ones = np.ones((len(points_w), 1), dtype=np.float64)
    pts_h = np.hstack([points_w, ones])
    cam   = (view_matrix @ pts_h.T).T
    clip  = (proj_mat @ cam.T).T
    w = clip[:, 3]
    safe_w = np.where(np.abs(w) > 1e-12, w, 1e-12)
    ndc_x = clip[:, 0] / safe_w
    ndc_y = clip[:, 1] / safe_w
    screen_x = (ndc_x + 1.0) * 0.5
    screen_y = (1.0 - ndc_y) * 0.5  # Y flipped: NDC +1 is top, screen 0 is top
    return np.stack([screen_x, screen_y], axis=1), w


def bilinear_sample(density: np.ndarray, screen_xy: np.ndarray) -> np.ndarray:
    """Sample a 2-D density array at fractional screen coordinates.

    screen_xy: (N, 2), values in [0, 1].  Out-of-bounds → 0.
    density:   (H, W) float array.
    Returns:   (N,) float array.
    """
    H, W = density.shape
    gx = screen_xy[:, 0] * (W - 1)
    gy = screen_xy[:, 1] * (H - 1)

    x0 = np.clip(np.floor(gx).astype(int), 0, W - 2)
    y0 = np.clip(np.floor(gy).astype(int), 0, H - 2)
    x1, y1 = x0 + 1, y0 + 1
    dx = gx - x0
    dy = gy - y0

    val = (
        density[y0, x0] * (1 - dx) * (1 - dy)
        + density[y0, x1] * dx       * (1 - dy)
        + density[y1, x0] * (1 - dx) * dy
        + density[y1, x1] * dx       * dy
    )
    oob = (screen_xy[:, 0] < 0) | (screen_xy[:, 0] > 1) | \
          (screen_xy[:, 1] < 0) | (screen_xy[:, 1] > 1)
    val[oob] = 0.0
    return val


def _normalize_sum(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    total = float(values.sum())
    if total <= 0.0 or not np.isfinite(total):
        return np.zeros_like(values)
    return values / total


def _normalize_minmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    vmin = float(values.min())
    vmax = float(values.max())
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        return np.zeros_like(values)
    return (values - vmin) / (vmax - vmin)


def _cosine_similarity(first: np.ndarray, second: np.ndarray) -> float:
    numerator = float(np.dot(first, second))
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def _nss(saliency_map: np.ndarray, fixation_mask: np.ndarray) -> float:
    saliency_map = np.asarray(saliency_map, dtype=np.float64)
    fixation_mask = np.asarray(fixation_mask, dtype=bool)
    if fixation_mask.sum() == 0:
        return 0.0
    std = float(saliency_map.std())
    if std == 0.0:
        return 0.0
    z_map = (saliency_map - saliency_map.mean()) / std
    return float(z_map[fixation_mask].mean())


def _auc_judd(saliency_map: np.ndarray, fixation_mask: np.ndarray) -> float:
    saliency_map = _normalize_minmax(saliency_map).reshape(-1)
    fixation_mask = np.asarray(fixation_mask, dtype=bool).reshape(-1)
    fixation_count = int(fixation_mask.sum())
    non_fixation_count = int((~fixation_mask).sum())
    if fixation_count == 0 or non_fixation_count == 0:
        return 0.5

    thresholds = np.sort(np.unique(saliency_map[fixation_mask]))[::-1]
    tp = [0.0]
    fp = [0.0]
    for threshold in thresholds:
        above = saliency_map >= threshold
        tp.append(float(np.logical_and(above, fixation_mask).sum()) / fixation_count)
        fp.append(float(np.logical_and(above, ~fixation_mask).sum()) / non_fixation_count)
    tp.append(1.0)
    fp.append(1.0)
    return float(np.trapezoid(np.asarray(tp), np.asarray(fp)))


def compute_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    proxy_fixation_percentiles: tuple[float, ...] = (90.0, 95.0, 99.0),
) -> dict[str, float]:
    pred = np.asarray(pred, dtype=np.float64).reshape(-1)
    gt = np.asarray(gt, dtype=np.float64).reshape(-1)

    lcc, _ = pearsonr(pred, gt)
    spearman_r, _ = spearmanr(pred, gt)

    pred_prob = _normalize_sum(np.clip(pred, a_min=0.0, a_max=None))
    gt_prob = _normalize_sum(np.clip(gt, a_min=0.0, a_max=None))
    pred_unit = _normalize_minmax(pred)
    gt_unit = _normalize_minmax(gt)

    eps = 1e-12
    pred_prob_safe = pred_prob + eps
    gt_prob_safe = gt_prob + eps

    metrics = {
        "CC": float(lcc),
        "LCC": float(lcc),
        "SIM": float(np.minimum(pred_prob, gt_prob).sum()),
        "KLD": float(np.sum(gt_prob_safe * np.log(gt_prob_safe / pred_prob_safe))),
        "MSE": float(np.mean((pred_unit - gt_unit) ** 2)),
        "MAE": float(np.mean(np.abs(pred_unit - gt_unit))),
        "Spearman": float(spearman_r),
        "Cosine": _cosine_similarity(pred, gt),
        "PredictionSum": float(pred.sum()),
        "GroundTruthSum": float(gt.sum()),
    }

    for percentile in proxy_fixation_percentiles:
        threshold = float(np.quantile(gt_unit, percentile / 100.0))
        fixation_mask = gt_unit >= threshold
        top_pct = 100.0 - percentile
        label = str(int(round(top_pct))) if math.isclose(top_pct, round(top_pct)) else str(top_pct).replace(".", "p")
        metrics[f"NSS_gt_top_{label}pct_proxy"] = _nss(pred_unit, fixation_mask)
        metrics[f"AUC_Judd_gt_top_{label}pct_proxy"] = _auc_judd(pred_unit, fixation_mask)
        metrics[f"GTMaskCount_top_{label}pct_proxy"] = float(fixation_mask.sum())

    return metrics


def _apply_transform_no_recenter(
    points: np.ndarray,
    camera_data: dict,
    rotation_z_rad: float,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
) -> np.ndarray:
    """Apply scale → rotZ → rotX → rotY → translate (no recentering).

    Used for face centroids where recentering was already applied once,
    outside the per-frame loop, using the vertex bounding-box center.
    """
    v = np.asarray(points, dtype=np.float64).copy()
    rz0 = math.radians(base_rotate_z_deg)
    if abs(rz0) > 1e-12:
        cz0, sz0 = math.cos(rz0), math.sin(rz0)
        x0 = cz0 * v[:, 0] - sz0 * v[:, 1]
        y0 = sz0 * v[:, 0] + cz0 * v[:, 1]
        v[:, 0], v[:, 1] = x0, y0

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


def run_screen_space(
    mesh: trimesh.Trimesh,
    camera_data: dict,
    gaze_batches: dict[int, FrameGazeBatch],
    sigma_screen: float,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    override_fov_deg: float | None,
) -> tuple[np.ndarray, dict]:
    n_faces = len(mesh.faces)
    face_sal = np.zeros(n_faces, dtype=np.float64)

    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]
    frames_list = camera_data["frames"]

    if override_fov_deg is not None:
        proj_mat = build_projection_matrix_from_fov(
            override_fov_deg, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]
        )
    else:
        proj_mat = np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4)

    view_matrix = np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)

    # Precompute face centroids once — applying vertex-bbox recenter if requested.
    # We do NOT copy the full mesh per frame; only the centroid array is transformed.
    base_centroids = np.asarray(mesh.triangles_center, dtype=np.float64)
    if recenter_to_bbox_center:
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        vert_bbox_center = 0.5 * (verts.min(axis=0) + verts.max(axis=0))
        base_centroids = base_centroids - vert_bbox_center

    sigma_px = sigma_screen * _IMG_W
    total_points = 0

    # Step 1 — per frame: build that frame's 2D density, then sample it on the
    # projected face centroids. Using one global density across all frames would
    # leak attention between different viewpoints of the rotating object.
    total_weight = 0.0
    frames_used  = 0
    for frame, batch in gaze_batches.items():
        n = int(batch.x_norm.size)
        if n == 0:
            continue
        if frame >= len(frames_list):
            continue

        hist = np.zeros((_IMG_H, _IMG_W), dtype=np.float64)
        px = np.clip((batch.x_norm * _IMG_W).astype(int), 0, _IMG_W - 1)
        py = np.clip((batch.y_norm * _IMG_H).astype(int), 0, _IMG_H - 1)
        np.add.at(hist, (py, px), 1.0)
        density = gaussian_filter(hist, sigma=sigma_px, mode="constant")
        density_sum = float(density.sum())
        if density_sum > 0.0:
            density /= density_sum

        total_points += n
        rot_z = float(frames_list[frame]["rotation_z_radians"])
        # Transform only the centroid array — O(n_faces), no BVH copy
        centroids_w = _apply_transform_no_recenter(
            base_centroids,
            camera_data,
            rot_z,
            base_rotate_z_deg,
            extra_rotate_x_deg,
            extra_rotate_y_deg,
        )

        screen_xy, w_clip = world_to_screen(centroids_w, view_matrix, proj_mat)
        # Mask faces behind the camera (w_clip <= 0 ↔ camera-space z ≥ 0)
        behind = w_clip <= 0
        screen_xy[behind] = -1.0  # force out-of-bounds so bilinear_sample returns 0

        sample = bilinear_sample(density, screen_xy)
        face_sal += n * sample
        total_weight += n
        frames_used += 1

    if total_weight > 0.0:
        face_sal /= total_weight

    stats = {
        "total_gaze_points":    total_points,
        "frames_used":          frames_used,
        "density_img_shape":    [_IMG_H, _IMG_W],
        "sigma_px":             sigma_px,
        "nonzero_faces":        int(np.count_nonzero(face_sal)),
    }
    return face_sal, stats


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

    tag_parts = [f"sigma{args.sigma_screen}".replace(".", "p")]
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
    tag = args.tag or "_".join(tag_parts)

    face_sal, run_stats = run_screen_space(
        mesh=mesh,
        camera_data=camera_data,
        gaze_batches=gaze_batches,
        sigma_screen=args.sigma_screen,
        recenter_to_bbox_center=bool(args.recenter_to_bbox_center),
        base_rotate_z_deg=args.base_rotate_z_deg,
        extra_rotate_x_deg=args.extra_rotate_x_deg,
        extra_rotate_y_deg=args.extra_rotate_y_deg,
        override_fov_deg=args.override_fov_deg,
    )

    gt = np.loadtxt(paths["gt"])
    if len(gt) != len(mesh.faces):
        raise SystemExit(
            f"GT face count mismatch: GT has {len(gt)} entries, mesh has {len(mesh.faces)} faces."
        )

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_screen_space_faces.txt", face_sal, fmt="%.10f")

    results = {"screen_space_gaussian": compute_metrics(face_sal, gt)}

    report = {
        "model":   args.model,
        "tag":     tag,
        "dataset": "MeshMamba_non_texture",
        "gt_file": str(paths["gt"].name),
        "n_faces": int(len(mesh.faces)),
        "gaze_stats":  gaze_stats,
        "run_stats":   run_stats,
        "method_params": {
            "sigma_screen":            args.sigma_screen,
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg":       args.base_rotate_z_deg,
            "extra_rotate_x_deg":      args.extra_rotate_x_deg,
            "extra_rotate_y_deg":      args.extra_rotate_y_deg,
            "override_fov_deg":        args.override_fov_deg,
            "transform_order": "base_rotate_z -> recenter -> scale -> rotation_z -> extra_rotate_x -> extra_rotate_y -> translation",
            "density_image":   f"{_IMG_W}x{_IMG_H}",
        },
        "metrics_vs_gt": results,
    }

    report_path = out_dir / f"{args.model}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()

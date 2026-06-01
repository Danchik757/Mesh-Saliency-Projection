#!/usr/bin/env python3
"""
Evaluate screen_space_gaussian on one 3DVA model (per-vertex output).

Method (screen_space_gaussian v2):
  1. Accumulate all gaze points into a 2D density image at full 1920×1080 resolution
     using bilinear deposition (not nearest-neighbour) and convolve with Gaussian
     sigma = --sigma-px pixels (default 49 px ≈ 1° of visual angle in the 3DVA paper
     setup: Tobii TX-120, 90 cm distance, 30" monitor at 1920×1080).
  2. For each animation frame that has gaze data, transform mesh vertices to world
     space and project them to screen coordinates using the JSON camera matrices.
  3. Sample the gaze density image at each vertex's screen position (bilinear).
  4. Accumulate contributions weighted by the number of gaze points in that frame.
  5. Compare the resulting per-vertex saliency map against the per-vertex GT TXT
     for views 300, 413, and 599.
     Two metric sections are reported:
       metrics_vs_gt_full        — all vertices (comparable to our own internal runs)
       metrics_vs_gt_visible_only — restricted to vertices visible from each GT view,
                                    as done in the original 3DVA paper (Section 5.2).

Sigma note (v1 → v2 fix):
  v1 used _IMG_W=256, sigma_screen=0.05 → sigma = 0.05×256 = 12.8 px at 256px
           = 96 px equivalent at 1920px  (3.6× too wide).
  v2 uses _IMG_W=1920, --sigma-px=49.0 → 49 px at 1920px  (correct).

GT granularity: per-vertex TXT (one float per line, N_vertices lines).
GT views:       300, 413, 599  — three static camera distances used in Experiment 2
                of the paper.  Each view has a matching visibility TXT (0/1 per vertex)
                in CentricityAndVisibilityMaps/.
JSON prefix:    3DVA_<model>.json
OBJ subdir:     3DModels-Simplif-up/<model>.obj   (corrected-orientation copies)

Env vars (used when CLI args are not provided):
  VISUAL_ATTENTION_3D_SHAPES_ROOT  — root of the 3DVA dataset
  THREE_DVA_CSV_ROOT               — directory with per-model CSV gaze files
  THREE_DVA_JSON_ROOT              — directory with per-model JSON camera/animation files
  THREE_DVA_OUTPUT_DIR             — output directory
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

# Density image resolution — full 1920×1080 (v2).
# Sigma is specified in absolute pixels at this resolution.
_IMG_W = 1920
_IMG_H = 1080

# Default sigma: 49 px at 1920×1080 ≈ 1° of visual angle in the 3DVA paper setup
# (Tobii TX-120, ~90 cm observer-to-screen, 30" Eizo monitor at 1920×1080).
_DEFAULT_SIGMA_PX = 49.0


@dataclass
class FrameGazeBatch:
    x_norm: np.ndarray
    y_norm: np.ndarray


def _env_path(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var, fallback))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate screen_space_gaussian (v2) on one 3DVA model (per-vertex). "
            "Uses full 1920×1080 density image and sigma-px in absolute pixels."
        )
    )
    parser.add_argument("--model", default="bunny", help="3DVA model name, e.g. bunny or A380.")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("VISUAL_ATTENTION_3D_SHAPES_ROOT", "e.g. /srv/datasets/3DVA"),
        help="Root of the 3DVA dataset (3DModels-Simplif-up, FixationMaps, CentricityAndVisibilityMaps, ...).",
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
            str(REPO_ROOT / "results" / "3dva" / "screen_space_gaussian"),
        ),
        help="Output directory for saliency maps and the evaluation report.",
    )
    parser.add_argument(
        "--sigma-px",
        type=float,
        default=_DEFAULT_SIGMA_PX,
        help=(
            f"Gaussian sigma in absolute pixels at {_IMG_W}×{_IMG_H} resolution "
            f"(default {_DEFAULT_SIGMA_PX} px ≈ 1° visual angle, 3DVA paper setup). "
            "v1 used sigma_screen=0.05 (fraction of width) which equals 96 px at 1920px — too wide."
        ),
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
        default=35.9834,
        help="Override projection vertical FOV in degrees. Default 35.9834 corresponds to 60° horizontal on 16:9.",
    )
    parser.add_argument(
        "--video-id",
        type=int,
        default=None,
        help="Optional filter for mixed-session CSVs such as 3DVA A380.",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Output sub-directory tag. Auto-derived from sigma and transform params if omitted.",
    )
    return parser.parse_args()


# ── file resolution helpers ─────────────────────────────────────────────────

def _candidate_model_names(model: str) -> list[str]:
    raw = model.strip()
    variants = [raw, raw.lower(), raw.upper()]
    deduped: list[str] = []
    seen: set[str] = set()
    for v in variants:
        if v.lower() not in seen:
            deduped.append(v)
            seen.add(v.lower())
    return deduped


def _casefold_file_lookup(directory: Path, suffix: str) -> dict[str, Path]:
    return {
        path.name.lower(): path
        for path in sorted(directory.glob(f"*{suffix}"))
        if path.is_file()
    }


def _resolve_casefold_file(directory: Path, candidate_names: list[str], suffix: str) -> Path | None:
    index = _casefold_file_lookup(directory, suffix)
    for name in candidate_names:
        resolved = index.get(f"{name}{suffix}".lower())
        if resolved is not None:
            return resolved
    return None


def _resolve_3dva_prefixed_json(json_root: Path, model: str) -> Path:
    candidate_names = [f"3DVA_{name}" for name in _candidate_model_names(model)]
    resolved = _resolve_casefold_file(json_root, candidate_names, ".json")
    if resolved is not None:
        return resolved
    raise FileNotFoundError(f"JSON file not found for model '{model}' in {json_root}")


def _resolve_gt_file(gt_root: Path, model: str, view: str) -> Path:
    candidate_names = [f"{name}_{view}norm" for name in _candidate_model_names(model)]
    resolved = _resolve_casefold_file(gt_root, candidate_names, ".txt")
    if resolved is not None:
        return resolved
    raise FileNotFoundError(f"GT file not found for model '{model}', view '{view}' in {gt_root}")


def _resolve_visibility_file(vis_root: Path, model: str, view: str) -> Path | None:
    """Return the visibility file for (model, view) or None if not available."""
    candidate_names = [f"{name}_{view}_visibility" for name in _candidate_model_names(model)]
    resolved = _resolve_casefold_file(vis_root, candidate_names, ".txt")
    return resolved  # None if missing (caller decides whether to warn or skip)


def resolve_model_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    candidate_names = _candidate_model_names(args.model)
    csv_path = _resolve_casefold_file(args.csv_root, candidate_names, ".csv")
    obj_path = _resolve_casefold_file(args.dataset_root / "3DModels-Simplif-up", candidate_names, ".obj")
    if csv_path is None:
        raise FileNotFoundError(f"CSV file not found for model '{args.model}' in {args.csv_root}")
    if obj_path is None:
        raise FileNotFoundError(
            f"OBJ file not found for model '{args.model}' in {args.dataset_root / '3DModels-Simplif-up'}"
        )
    vis_root = args.dataset_root / "CentricityAndVisibilityMaps"
    return {
        "csv":    csv_path,
        "json":   _resolve_3dva_prefixed_json(args.json_root, args.model),
        "obj":    obj_path,
        "gt_300": _resolve_gt_file(args.dataset_root / "FixationMaps", args.model, "300"),
        "gt_413": _resolve_gt_file(args.dataset_root / "FixationMaps", args.model, "413"),
        "gt_599": _resolve_gt_file(args.dataset_root / "FixationMaps", args.model, "599"),
        "vis_300": _resolve_visibility_file(vis_root, args.model, "300"),
        "vis_413": _resolve_visibility_file(vis_root, args.model, "413"),
        "vis_599": _resolve_visibility_file(vis_root, args.model, "599"),
    }


def ensure_required_exist(paths: dict[str, Path | None]) -> None:
    required_keys = ["csv", "json", "obj", "gt_300", "gt_413", "gt_599"]
    missing = [f"{name}: {paths[name]}" for name in required_keys if paths[name] is None or not paths[name].exists()]
    if missing:
        raise SystemExit("Missing required inputs:\n" + "\n".join(missing))


# ── gaze loading ─────────────────────────────────────────────────────────────

def load_gaze_batches(
    csv_path: Path, fps: int, total_frames: int, video_id: int | None = None
) -> tuple[dict[int, FrameGazeBatch], dict]:
    df = pd.read_csv(csv_path)
    unique_video_ids = sorted(int(v) for v in df["video_id"].dropna().unique()) if "video_id" in df.columns else []
    if video_id is not None:
        if "video_id" not in df.columns:
            raise ValueError(f"--video-id={video_id} was provided, but CSV has no video_id column: {csv_path}")
        df = df[df["video_id"] == video_id].copy()
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
        "video_id_filter": int(video_id) if video_id is not None else None,
        "video_ids_present": unique_video_ids,
        "video_ids_mixed": len(unique_video_ids) > 1,
    }
    return batches, stats


# ── projection helpers ────────────────────────────────────────────────────────

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


def _apply_transform_no_recenter(
    points: np.ndarray,
    camera_data: dict,
    rotation_z_rad: float,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
) -> np.ndarray:
    """Apply base_rotZ → scale → rotZ(frame) → rotX → rotY → translate (no vertex recentering).

    Vertex recentering is applied once outside the frame loop; only per-frame
    rotation/scale/translate is handled here (O(n_verts), no BVH copy needed).
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


def world_to_screen(
    points_w: np.ndarray,
    view_matrix: np.ndarray,
    proj_mat: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    ones = np.ones((len(points_w), 1), dtype=np.float64)
    pts_h = np.hstack([points_w, ones])
    cam  = (view_matrix @ pts_h.T).T
    clip = (proj_mat @ cam.T).T
    w = clip[:, 3]
    safe_w = np.where(np.abs(w) > 1e-12, w, 1e-12)
    ndc_x = clip[:, 0] / safe_w
    ndc_y = clip[:, 1] / safe_w
    screen_x = (ndc_x + 1.0) * 0.5
    screen_y = (1.0 - ndc_y) * 0.5
    return np.stack([screen_x, screen_y], axis=1), w


def bilinear_deposit(hist: np.ndarray, x_norm: np.ndarray, y_norm: np.ndarray) -> None:
    """Deposit gaze points into hist using bilinear interpolation (in-place)."""
    H, W = hist.shape
    gx = x_norm * (W - 1)
    gy = y_norm * (H - 1)
    x0 = np.clip(np.floor(gx).astype(int), 0, W - 2)
    y0 = np.clip(np.floor(gy).astype(int), 0, H - 2)
    x1, y1 = x0 + 1, y0 + 1
    dx = gx - x0
    dy = gy - y0
    np.add.at(hist, (y0, x0), (1 - dx) * (1 - dy))
    np.add.at(hist, (y0, x1), dx       * (1 - dy))
    np.add.at(hist, (y1, x0), (1 - dx) * dy)
    np.add.at(hist, (y1, x1), dx       * dy)


def bilinear_sample(density: np.ndarray, screen_xy: np.ndarray) -> np.ndarray:
    H, W = density.shape
    gx = screen_xy[:, 0] * (W - 1)
    gy = screen_xy[:, 1] * (H - 1)
    x0 = np.clip(np.floor(gx).astype(int), 0, W - 2)
    y0 = np.clip(np.floor(gy).astype(int), 0, H - 2)
    x1, y1 = x0 + 1, y0 + 1
    dx, dy = gx - x0, gy - y0
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


# ── metrics ──────────────────────────────────────────────────────────────────

def _normalize_sum(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    total = float(values.sum())
    if total <= 0.0 or not np.isfinite(total):
        return np.zeros_like(values)
    return values / total


def _normalize_minmax(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    vmin, vmax = float(values.min()), float(values.max())
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        return np.zeros_like(values)
    return (values - vmin) / (vmax - vmin)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b)) / denom if denom != 0.0 else 0.0


def _nss(saliency_map: np.ndarray, fixation_mask: np.ndarray) -> float:
    saliency_map = np.asarray(saliency_map, dtype=np.float64)
    fixation_mask = np.asarray(fixation_mask, dtype=bool)
    if fixation_mask.sum() == 0:
        return 0.0
    std = float(saliency_map.std())
    if std == 0.0:
        return 0.0
    return float(((saliency_map - saliency_map.mean()) / std)[fixation_mask].mean())


def _auc_judd(saliency_map: np.ndarray, fixation_mask: np.ndarray) -> float:
    saliency_map = _normalize_minmax(saliency_map).reshape(-1)
    fixation_mask = np.asarray(fixation_mask, dtype=bool).reshape(-1)
    n_pos = int(fixation_mask.sum())
    n_neg = int((~fixation_mask).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.5
    thresholds = np.sort(np.unique(saliency_map[fixation_mask]))[::-1]
    tp, fp = [0.0], [0.0]
    for thr in thresholds:
        above = saliency_map >= thr
        tp.append(float(np.logical_and(above,  fixation_mask).sum()) / n_pos)
        fp.append(float(np.logical_and(above, ~fixation_mask).sum()) / n_neg)
    tp.append(1.0)
    fp.append(1.0)
    return float(np.trapezoid(np.asarray(tp), np.asarray(fp)))


def compute_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    proxy_fixation_percentiles: tuple[float, ...] = (90.0, 95.0, 99.0),
) -> dict[str, float]:
    """Compute full metric set between pred and gt (both same length, full or masked slice)."""
    pred = np.asarray(pred, dtype=np.float64).reshape(-1)
    gt   = np.asarray(gt,   dtype=np.float64).reshape(-1)

    lcc, _        = pearsonr(pred, gt)
    spearman_r, _ = spearmanr(pred, gt)

    pred_prob = _normalize_sum(np.clip(pred, 0.0, None))
    gt_prob   = _normalize_sum(np.clip(gt,   0.0, None))
    pred_unit = _normalize_minmax(pred)
    gt_unit   = _normalize_minmax(gt)

    eps = 1e-12
    metrics = {
        "CC":       float(lcc),
        "LCC":      float(lcc),
        "SIM":      float(np.minimum(pred_prob, gt_prob).sum()),
        "KLD":      float(np.sum((gt_prob + eps) * np.log((gt_prob + eps) / (pred_prob + eps)))),
        "MSE":      float(np.mean((pred_unit - gt_unit) ** 2)),
        "MAE":      float(np.mean(np.abs(pred_unit - gt_unit))),
        "Spearman": float(spearman_r),
        "Cosine":   _cosine_similarity(pred, gt),
        "PredictionSum":  float(pred.sum()),
        "GroundTruthSum": float(gt.sum()),
        "n_vertices": int(len(pred)),
    }

    for percentile in proxy_fixation_percentiles:
        threshold     = float(np.quantile(gt_unit, percentile / 100.0))
        fixation_mask = gt_unit >= threshold
        top_pct = 100.0 - percentile
        label = str(int(round(top_pct))) if math.isclose(top_pct, round(top_pct)) else str(top_pct).replace(".", "p")
        metrics[f"NSS_gt_top_{label}pct_proxy"]       = _nss(pred_unit, fixation_mask)
        metrics[f"AUC_Judd_gt_top_{label}pct_proxy"]  = _auc_judd(pred_unit, fixation_mask)
        metrics[f"GTMaskCount_top_{label}pct_proxy"]  = float(fixation_mask.sum())

    return metrics


# ── main projection ───────────────────────────────────────────────────────────

def run_screen_space(
    mesh: trimesh.Trimesh,
    camera_data: dict,
    gaze_batches: dict[int, FrameGazeBatch],
    sigma_px: float,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    override_fov_deg: float | None,
) -> tuple[np.ndarray, dict]:
    """Project gaze density onto mesh vertices and return per-vertex saliency."""
    n_verts  = len(mesh.vertices)
    vert_sal = np.zeros(n_verts, dtype=np.float64)

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

    # Precompute vertex positions once: apply bbox recentering if requested,
    # outside the per-frame loop so we avoid re-computing it N_frames times.
    base_verts = np.asarray(mesh.vertices, dtype=np.float64).copy()
    if recenter_to_bbox_center:
        bbox_center = 0.5 * (base_verts.min(axis=0) + base_verts.max(axis=0))
        base_verts -= bbox_center

    total_points = 0
    total_weight = 0.0
    frames_used  = 0

    for frame, batch in gaze_batches.items():
        n = int(batch.x_norm.size)
        if n == 0:
            continue
        if frame >= len(frames_list):
            continue

        # Build density image with bilinear deposition (v2: avoids aliasing at 1920px).
        hist = np.zeros((_IMG_H, _IMG_W), dtype=np.float64)
        bilinear_deposit(hist, batch.x_norm, batch.y_norm)
        density = gaussian_filter(hist, sigma=sigma_px, mode="constant")
        density_sum = float(density.sum())
        if density_sum > 0.0:
            density /= density_sum

        total_points += n
        rot_z = float(frames_list[frame]["rotation_z_radians"])
        verts_w = _apply_transform_no_recenter(
            base_verts, camera_data, rot_z,
            base_rotate_z_deg, extra_rotate_x_deg, extra_rotate_y_deg,
        )

        screen_xy, w_clip = world_to_screen(verts_w, view_matrix, proj_mat)
        screen_xy[w_clip <= 0] = -1.0  # behind camera → out of bounds → 0
        sample = bilinear_sample(density, screen_xy)
        vert_sal    += n * sample
        total_weight += n
        frames_used  += 1

    if total_weight > 0.0:
        vert_sal /= total_weight

    stats = {
        "total_gaze_points":     total_points,
        "frames_used":           frames_used,
        "density_img_shape":     [_IMG_H, _IMG_W],
        "sigma_px":              sigma_px,
        "nonzero_vertices":      int(np.count_nonzero(vert_sal)),
        "deposition":            "bilinear",
    }
    return vert_sal, stats


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args  = parse_args()
    paths = resolve_model_paths(args)
    ensure_required_exist(paths)

    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)
    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected a single Trimesh, got {type(mesh)}")

    gaze_batches, gaze_stats = load_gaze_batches(
        paths["csv"],
        fps=int(camera_data["video_info"]["fps"]),
        total_frames=int(camera_data["video_info"]["total_frames"]),
        video_id=args.video_id,
    )

    tag_parts = [f"sigpx{args.sigma_px}".replace(".", "p")]
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

    vert_sal, run_stats = run_screen_space(
        mesh=mesh,
        camera_data=camera_data,
        gaze_batches=gaze_batches,
        sigma_px=args.sigma_px,
        recenter_to_bbox_center=bool(args.recenter_to_bbox_center),
        base_rotate_z_deg=args.base_rotate_z_deg,
        extra_rotate_x_deg=args.extra_rotate_x_deg,
        extra_rotate_y_deg=args.extra_rotate_y_deg,
        override_fov_deg=args.override_fov_deg,
    )

    # Load GT and visibility maps.
    results: dict[str, dict] = {}
    vis_stats: dict[str, dict] = {}
    for view in ("300", "413", "599"):
        gt = np.loadtxt(paths[f"gt_{view}"])
        if len(gt) != len(mesh.vertices):
            raise SystemExit(
                f"GT vertex count mismatch for view {view}: "
                f"GT has {len(gt)} entries, mesh has {len(mesh.vertices)} vertices."
            )

        # --- full-mesh metrics (all vertices) ---
        metrics_full = compute_metrics(vert_sal, gt)

        # --- visibility-masked metrics (visible vertices only) ---
        vis_path = paths.get(f"vis_{view}")
        if vis_path is not None and vis_path.exists():
            vis = np.loadtxt(vis_path).astype(bool)
            if len(vis) != len(mesh.vertices):
                print(f"[warn] visibility file length mismatch for view {view}, skipping mask", flush=True)
                metrics_vis = None
            else:
                n_vis = int(vis.sum())
                metrics_vis = compute_metrics(vert_sal[vis], gt[vis])
                vis_stats[view] = {"n_visible": n_vis, "n_total": int(len(vis))}
        else:
            print(f"[warn] no visibility file for view {view}, skipping masked metrics", flush=True)
            metrics_vis = None

        results[view] = {
            "metrics_vs_gt_full":         metrics_full,
            "metrics_vs_gt_visible_only":  metrics_vis,
        }

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_screen_space_vertices.txt", vert_sal, fmt="%.10f")

    report = {
        "model":      args.model,
        "tag":        tag,
        "dataset":    "3DVA",
        "script_version": "v2",
        "n_vertices": int(len(mesh.vertices)),
        "gaze_stats": gaze_stats,
        "run_stats":  run_stats,
        "visibility_stats": vis_stats,
        "method_params": {
            "sigma_px":                args.sigma_px,
            "density_img":             f"{_IMG_W}x{_IMG_H}",
            "deposition":              "bilinear",
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg":       args.base_rotate_z_deg,
            "extra_rotate_x_deg":      args.extra_rotate_x_deg,
            "extra_rotate_y_deg":      args.extra_rotate_y_deg,
            "override_fov_deg":        args.override_fov_deg,
            "video_id":                args.video_id,
            "transform_order": (
                "base_rotate_z -> recenter -> scale -> rotation_z "
                "-> extra_rotate_x -> extra_rotate_y -> translation"
            ),
            "v1_note": (
                "v1 used _IMG_W=256, sigma_screen=0.05 → sigma=12.8px@256 = 96px@1920 (too wide). "
                "v2 uses _IMG_W=1920, sigma_px=49.0 (≈1° visual angle, 3DVA paper setup)."
            ),
        },
        "metrics_note": (
            "metrics_vs_gt_full: all mesh vertices. "
            "metrics_vs_gt_visible_only: restricted to vertices visible from each GT static view "
            "(CentricityAndVisibilityMaps/*.visibility.txt); this matches the paper's evaluation protocol."
        ),
        "metrics_vs_gt": results,
    }

    report_path = out_dir / f"{args.model}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}", flush=True)


if __name__ == "__main__":
    main()

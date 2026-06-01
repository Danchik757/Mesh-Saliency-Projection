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
import re
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
        description="Evaluate screen_space_gaussian on one MeshMamba model (non_texture or rgb_texture)."
    )
    parser.add_argument("--model", default="Starfruit_L3", help="MeshMamba model name.")
    parser.add_argument(
        "--texture-type",
        choices=["non_texture", "rgb_texture"],
        default="non_texture",
        help="MeshMamba texture type: 'non_texture' or 'rgb_texture'.",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("MESHMAMBA_NON_TEXTURE_ROOT", "e.g. /srv/datasets/MeshMambaSaliency"),
        help="Dataset root containing MeshFile/{texture_type} and SaliencyMap/{texture_type}.",
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
        default=True,
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
        default=90.0,
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
        "--projection-fov-mode",
        choices=["vertical", "horizontal_to_vertical", "json"],
        default="horizontal_to_vertical",
        help=(
            "How to interpret FOV for the projection matrix. "
            "'vertical' keeps legacy behavior: override FOV is vertical, no override uses JSON matrix. "
            "'horizontal_to_vertical' treats override/JSON FOV as horizontal and converts it to vertical. "
            "'json' always uses the JSON projection matrix."
        ),
    )
    parser.add_argument(
        "--transform-order",
        choices=["eval", "blender_rig"],
        default="blender_rig",
        help=(
            "Mesh transform order. 'eval' is legacy; 'blender_rig' matches the Blender preview rig "
            "where local object rotations happen before per-frame parent Z rotation."
        ),
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Output sub-directory tag. Auto-derived from transform params if omitted.",
    )
    return parser.parse_args()


def _candidate_model_names(model: str) -> list[str]:
    raw = model.strip()
    variants = [raw, raw.replace("_", "-"), raw.replace("-", "_")]
    stripped = re.sub(r"([_-])l\d+$", "", raw, flags=re.IGNORECASE)
    if stripped != raw:
        variants.extend([stripped, stripped.replace("_", "-"), stripped.replace("-", "_")])

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = variant.lower()
        if key not in seen:
            deduped.append(variant)
            seen.add(key)
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


def find_gt_file(gt_dir: Path, model: str, extra_candidate_names: list[str] | None = None) -> Path:
    candidate_names = _candidate_model_names(model)
    if extra_candidate_names:
        candidate_names.extend(extra_candidate_names)
    resolved = _resolve_casefold_file(gt_dir, candidate_names, ".csv")
    if resolved is not None:
        return resolved
    model_norms = {
        name.lower().replace("_", "-").replace(" ", "-")
        for name in candidate_names
    }
    for f in sorted(gt_dir.glob("*.csv")):
        if f.stem.lower().replace("_", "-").replace(" ", "-") in model_norms:
            return f
    available = ", ".join(f.name for f in sorted(gt_dir.glob("*.csv")))
    raise FileNotFoundError(
        f"GT file not found for model '{model}' in {gt_dir}.\n"
        f"Tried: {', '.join(f'{name}.csv' for name in candidate_names)}\n"
        f"Available: {available}"
    )


def find_obj_file(mesh_dir: Path, model: str) -> Path:
    dir_index = {
        path.name.lower(): path
        for path in sorted(mesh_dir.iterdir())
        if path.is_dir()
    }
    model_dir = None
    candidate_names = _candidate_model_names(model)
    for name in candidate_names:
        model_dir = dir_index.get(name.lower())
        if model_dir is not None:
            break
    if model_dir is None:
        raise FileNotFoundError(
            f"Model directory not found for '{model}' in {mesh_dir}. "
            f"Tried: {', '.join(candidate_names)}"
        )
    resolved = _resolve_casefold_file(model_dir, candidate_names, ".obj")
    if resolved is not None:
        return resolved
    obj_candidates = _casefold_file_lookup(model_dir, ".obj")
    if obj_candidates:
        return sorted(obj_candidates.values())[0]
    raise FileNotFoundError(f"No OBJ file found in {model_dir}")


def find_csv_file(csv_root: Path, model: str) -> Path:
    candidate_names = _candidate_model_names(model)
    resolved = _resolve_casefold_file(csv_root, candidate_names, ".csv")
    if resolved is not None:
        return resolved
    raise FileNotFoundError(f"CSV file not found for model '{model}' in {csv_root}")


def find_json_file(json_root: Path, model: str, texture_type: str = "non_texture") -> Path:
    prefix = f"MeshMamba_{texture_type}_"
    candidate_names = [f"{prefix}{name}" for name in _candidate_model_names(model)]
    resolved = _resolve_casefold_file(json_root, candidate_names, ".json")
    if resolved is not None:
        return resolved
    raise FileNotFoundError(f"JSON file not found for model '{model}' (prefix={prefix}) in {json_root}")


def resolve_model_paths(args: argparse.Namespace) -> dict[str, Path]:
    texture_type = args.texture_type
    mesh_dir = args.dataset_root / "MeshFile" / texture_type
    gt_dir   = args.dataset_root / "SaliencyMap" / texture_type
    obj_path = find_obj_file(mesh_dir, args.model)
    gt_candidates = [obj_path.stem]
    resolved_stem = obj_path.resolve().stem
    if resolved_stem not in gt_candidates:
        gt_candidates.append(resolved_stem)
    gt_path  = find_gt_file(gt_dir, args.model, extra_candidate_names=gt_candidates)
    return {
        "csv":  find_csv_file(args.csv_root, args.model),
        "json": find_json_file(args.json_root, args.model, texture_type),
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


def horizontal_to_vertical_fov_deg(horizontal_fov_deg: float, aspect_ratio: float) -> float:
    return math.degrees(
        2.0 * math.atan(math.tan(math.radians(horizontal_fov_deg) * 0.5) / float(aspect_ratio))
    )


def resolve_projection_matrix(
    camera_data: dict,
    override_fov_deg: float | None,
    projection_fov_mode: str,
) -> tuple[np.ndarray, dict[str, float | str | None]]:
    cam = camera_data["camera_static"]
    vi = camera_data["video_info"]

    if projection_fov_mode == "json":
        if override_fov_deg is not None:
            raise ValueError("--projection-fov-mode json cannot be combined with --override-fov-deg")
        return np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4), {
            "projection_fov_mode": "json",
            "projection_fov_source": "json_projection_matrix",
            "input_fov_deg": None,
            "effective_vertical_fov_deg": None,
        }

    if projection_fov_mode == "vertical":
        if override_fov_deg is None:
            return np.asarray(cam["projection_matrix"], dtype=np.float64).reshape(4, 4), {
                "projection_fov_mode": "vertical",
                "projection_fov_source": "json_projection_matrix",
                "input_fov_deg": None,
                "effective_vertical_fov_deg": None,
            }
        effective_fov = float(override_fov_deg)
        return build_projection_matrix_from_fov(
            effective_fov, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]
        ), {
            "projection_fov_mode": "vertical",
            "projection_fov_source": "override_fov_deg",
            "input_fov_deg": float(override_fov_deg),
            "effective_vertical_fov_deg": effective_fov,
        }

    if projection_fov_mode == "horizontal_to_vertical":
        if override_fov_deg is None:
            if "fov_degrees" in cam:
                input_fov = float(cam["fov_degrees"])
                source = "json_camera_static.fov_degrees"
            else:
                input_fov = math.degrees(float(cam["fov_radians"]))
                source = "json_camera_static.fov_radians"
        else:
            input_fov = float(override_fov_deg)
            source = "override_fov_deg"
        effective_fov = horizontal_to_vertical_fov_deg(input_fov, float(vi["aspect_ratio"]))
        return build_projection_matrix_from_fov(
            effective_fov, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]
        ), {
            "projection_fov_mode": "horizontal_to_vertical",
            "projection_fov_source": source,
            "input_fov_deg": input_fov,
            "effective_vertical_fov_deg": effective_fov,
        }

    raise ValueError(f"Unsupported projection_fov_mode: {projection_fov_mode}")


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
    """Full per-frame vertex transform (not used in the main screen-space loop,
    which uses _apply_transform_no_recenter instead; kept for reference).

    `eval` preserves the legacy benchmark order. `blender_rig` mirrors the
    Blender canonical preview: local object rotations before parent frame-Z.
    """
    v = np.asarray(vertices, dtype=np.float64).copy()
    bbox_center = 0.5 * (v.min(axis=0) + v.max(axis=0))

    def rotate_z(points: np.ndarray, angle_rad: float) -> np.ndarray:
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        cz, sz = math.cos(angle_rad), math.sin(angle_rad)
        x = cz * points[:, 0] - sz * points[:, 1]
        y = sz * points[:, 0] + cz * points[:, 1]
        out[:, 0], out[:, 1] = x, y
        return out

    def rotate_x(points: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_rad = math.radians(angle_deg)
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        crx, srx = math.cos(angle_rad), math.sin(angle_rad)
        y = crx * points[:, 1] - srx * points[:, 2]
        z = srx * points[:, 1] + crx * points[:, 2]
        out[:, 1], out[:, 2] = y, z
        return out

    def rotate_y(points: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_rad = math.radians(angle_deg)
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        cry, sry = math.cos(angle_rad), math.sin(angle_rad)
        x = cry * points[:, 0] + sry * points[:, 2]
        z = -sry * points[:, 0] + cry * points[:, 2]
        out[:, 0], out[:, 2] = x, z
        return out

    scale = np.asarray(camera_data["model_static"]["scale"], dtype=np.float64)
    base_rotate_z_rad = math.radians(base_rotate_z_deg)

    if transform_order == "eval":
        v = rotate_z(v, base_rotate_z_rad)
        if recenter_to_bbox_center:
            v -= bbox_center
        v *= scale
        v = rotate_z(v, rotation_z_rad)
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
    elif transform_order == "blender_rig":
        if recenter_to_bbox_center:
            v -= bbox_center
        v *= scale
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
        v = rotate_z(v, base_rotate_z_rad)
        v = rotate_z(v, rotation_z_rad)
    else:
        raise ValueError(f"Unsupported transform order: {transform_order}")

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
    transform_order: str,
) -> np.ndarray:
    """Apply per-frame transform to points that were already recentered."""
    v = np.asarray(points, dtype=np.float64).copy()

    def rotate_z(points: np.ndarray, angle_rad: float) -> np.ndarray:
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        cz, sz = math.cos(angle_rad), math.sin(angle_rad)
        x = cz * points[:, 0] - sz * points[:, 1]
        y = sz * points[:, 0] + cz * points[:, 1]
        out[:, 0], out[:, 1] = x, y
        return out

    def rotate_x(points: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_rad = math.radians(angle_deg)
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        crx, srx = math.cos(angle_rad), math.sin(angle_rad)
        y = crx * points[:, 1] - srx * points[:, 2]
        z = srx * points[:, 1] + crx * points[:, 2]
        out[:, 1], out[:, 2] = y, z
        return out

    def rotate_y(points: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_rad = math.radians(angle_deg)
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        cry, sry = math.cos(angle_rad), math.sin(angle_rad)
        x = cry * points[:, 0] + sry * points[:, 2]
        z = -sry * points[:, 0] + cry * points[:, 2]
        out[:, 0], out[:, 2] = x, z
        return out

    scale = np.asarray(camera_data["model_static"]["scale"], dtype=np.float64)
    base_rotate_z_rad = math.radians(base_rotate_z_deg)

    if transform_order == "eval":
        v = rotate_z(v, base_rotate_z_rad)
        v *= scale
        v = rotate_z(v, rotation_z_rad)
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
    elif transform_order == "blender_rig":
        v *= scale
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
        v = rotate_z(v, base_rotate_z_rad)
        v = rotate_z(v, rotation_z_rad)
    else:
        raise ValueError(f"Unsupported transform order: {transform_order}")

    v += np.asarray(camera_data["model_static"]["location"], dtype=np.float64)
    return v


def _apply_normal_transform(
    normals: np.ndarray,
    rotation_z_rad: float,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    transform_order: str,
) -> np.ndarray:
    """Rotate face normals with the same orientation chain as the mesh."""
    v = np.asarray(normals, dtype=np.float64).copy()

    def rotate_z(points: np.ndarray, angle_rad: float) -> np.ndarray:
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        cz, sz = math.cos(angle_rad), math.sin(angle_rad)
        x = cz * points[:, 0] - sz * points[:, 1]
        y = sz * points[:, 0] + cz * points[:, 1]
        out[:, 0], out[:, 1] = x, y
        return out

    def rotate_x(points: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_rad = math.radians(angle_deg)
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        crx, srx = math.cos(angle_rad), math.sin(angle_rad)
        y = crx * points[:, 1] - srx * points[:, 2]
        z = srx * points[:, 1] + crx * points[:, 2]
        out[:, 1], out[:, 2] = y, z
        return out

    def rotate_y(points: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_rad = math.radians(angle_deg)
        if abs(angle_rad) <= 1e-12:
            return points
        out = points.copy()
        cry, sry = math.cos(angle_rad), math.sin(angle_rad)
        x = cry * points[:, 0] + sry * points[:, 2]
        z = -sry * points[:, 0] + cry * points[:, 2]
        out[:, 0], out[:, 2] = x, z
        return out

    base_rotate_z_rad = math.radians(base_rotate_z_deg)

    if transform_order == "eval":
        v = rotate_z(v, base_rotate_z_rad)
        v = rotate_z(v, rotation_z_rad)
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
    elif transform_order == "blender_rig":
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
        v = rotate_z(v, base_rotate_z_rad)
        v = rotate_z(v, rotation_z_rad)
    else:
        raise ValueError(f"Unsupported transform order: {transform_order}")

    norm = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(norm > 1e-12, norm, 1.0)


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
    projection_fov_mode: str,
    transform_order: str,
) -> tuple[np.ndarray, dict]:
    n_faces = len(mesh.faces)
    face_sal = np.zeros(n_faces, dtype=np.float64)

    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]
    frames_list = camera_data["frames"]

    proj_mat, projection_info = resolve_projection_matrix(
        camera_data,
        override_fov_deg=override_fov_deg,
        projection_fov_mode=projection_fov_mode,
    )

    view_matrix = np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)

    # Precompute face centroids once — applying vertex-bbox recenter if requested.
    # We do NOT copy the full mesh per frame; only the centroid array is transformed.
    base_centroids = np.asarray(mesh.triangles_center, dtype=np.float64)
    base_normals = np.asarray(mesh.face_normals, dtype=np.float64)
    if recenter_to_bbox_center:
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        vert_bbox_center = 0.5 * (verts.min(axis=0) + verts.max(axis=0))
        base_centroids = base_centroids - vert_bbox_center

    sigma_px = sigma_screen * _IMG_W
    total_points = 0
    culled_back_faces = 0

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
            transform_order,
        )
        normals_w = _apply_normal_transform(
            base_normals,
            rot_z,
            base_rotate_z_deg,
            extra_rotate_x_deg,
            extra_rotate_y_deg,
            transform_order,
        )

        screen_xy, w_clip = world_to_screen(centroids_w, view_matrix, proj_mat)
        # Mask faces behind the camera (w_clip <= 0 ↔ camera-space z ≥ 0)
        behind = w_clip <= 0
        camera_world = np.linalg.inv(view_matrix)[:3, 3]
        to_camera = camera_world[None, :] - centroids_w
        front_facing = np.einsum("ij,ij->i", normals_w, to_camera) > 0.0
        culled_back_faces += int((~front_facing).sum())
        screen_xy[behind | (~front_facing)] = -1.0  # force out-of-bounds so bilinear_sample returns 0

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
        "culled_back_faces":    culled_back_faces,
        "projection":           projection_info,
    }
    return face_sal, stats


def main() -> None:
    args  = parse_args()
    paths = resolve_model_paths(args)
    ensure_exists(paths)

    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)
    mesh = trimesh.load(str(paths["obj"]), process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    if isinstance(mesh, (list, tuple)):
        mesh = trimesh.util.concatenate([m for m in mesh if isinstance(m, trimesh.Trimesh)])
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected a Trimesh-compatible OBJ, got {type(mesh)}")

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
    if args.projection_fov_mode != "vertical":
        tag_parts.append(args.projection_fov_mode.replace("_", ""))
    if args.transform_order != "eval":
        tag_parts.append(args.transform_order)
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
        projection_fov_mode=args.projection_fov_mode,
        transform_order=args.transform_order,
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
        "dataset": f"MeshMamba_{args.texture_type}",
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
            "projection_fov_mode":     args.projection_fov_mode,
            **run_stats["projection"],
            "transform_order":         args.transform_order,
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

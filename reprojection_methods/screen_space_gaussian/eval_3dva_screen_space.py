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
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter
from scipy.stats import pearsonr, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.participant_loader import GazeBatch, load_processed_track, load_csv_compat_track  # noqa: E402

# Density image resolution — full 1920×1080 (v2).
# Sigma is specified in absolute pixels at this resolution.
_IMG_W = 1920
_IMG_H = 1080

# Default sigma: 49 px at 1920×1080 ≈ 1° of visual angle in the 3DVA paper setup
# (Tobii TX-120, ~90 cm observer-to-screen, 30" Eizo monitor at 1920×1080).
_DEFAULT_SIGMA_PX = 49.0

FrameGazeBatch = GazeBatch


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
        help="Directory with per-model 3DVA CSV gaze files (only used with --csv-compat).",
    )
    parser.add_argument(
        "--fixation-root",
        type=Path,
        default=next(
            (Path(os.environ[k]) for k in (
                "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT",
                "THREE_DVA_PROCESSED_FIXATIONS_ROOT",
            ) if k in os.environ),
            None,
        ),
        help="Root of processed_fixations_offset_2000/. Required unless --csv-compat is set.",
    )
    parser.add_argument(
        "--csv-compat",
        action="store_true",
        default=False,
        help="Use legacy CSV input (requires --csv-root). Reports will show input_mode=csv_compat.",
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
        default=None,
        help=(
            "Override projection FOV in degrees. Interpretation depends on "
            "--projection-fov-mode."
        ),
    )
    parser.add_argument(
        "--projection-fov-mode",
        choices=("vertical", "horizontal_to_vertical", "json"),
        default="horizontal_to_vertical",
        help=(
            "How to resolve the projection matrix: "
            "'horizontal_to_vertical' converts the JSON horizontal FOV to the effective "
            "vertical FOV for the current aspect ratio; "
            "'vertical' treats --override-fov-deg as vertical FOV or falls back to the "
            "JSON projection matrix when no override is provided; "
            "'json' uses the projection matrix from JSON verbatim."
        ),
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
    obj_path = _resolve_casefold_file(args.dataset_root / "3DModels-Simplif-up", candidate_names, ".obj")
    if obj_path is None:
        raise FileNotFoundError(
            f"OBJ file not found for model '{args.model}' in {args.dataset_root / '3DModels-Simplif-up'}"
        )
    vis_root = args.dataset_root / "CentricityAndVisibilityMaps"
    return {
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
    required_keys = ["json", "obj", "gt_300", "gt_413", "gt_599"]
    missing = [f"{name}: {paths[name]}" for name in required_keys if paths[name] is None or not paths[name].exists()]
    if missing:
        raise SystemExit("Missing required inputs:\n" + "\n".join(missing))


# ── gaze loading ─────────────────────────────────────────────────────────────

def _load_gaze_track(args: argparse.Namespace, placement_path: Path):
    dataset        = "3DVA"
    model          = args.model
    canonical_name = f"3DVA_{model}"
    if args.csv_compat:
        candidate_names = _candidate_model_names(model)
        csv_path = _resolve_casefold_file(args.csv_root, candidate_names, ".csv")
        if csv_path is None:
            raise FileNotFoundError(f"CSV not found for '{model}' in {args.csv_root}")
        return load_csv_compat_track(
            csv_path, placement_path,
            dataset=dataset, model=model, canonical_name=canonical_name,
            video_id=getattr(args, "video_id", None),
        )
    if args.fixation_root is None:
        raise SystemExit("--fixation-root is required unless --csv-compat is set")
    return load_processed_track(
        args.fixation_root / canonical_name / "fixations.json",
        placement_path,
        dataset=dataset, model=model, canonical_name=canonical_name,
    )


def _gaze_stats(track) -> dict:
    return {
        "num_points":             sum(len(b.x_norm) for b in track.gaze_batches.values()),
        "num_frames_with_points": sum(1 for b in track.gaze_batches.values() if len(b.x_norm) > 0),
        "num_rows":               track.provenance.get("csv_num_rows"),
        "num_participants":       track.provenance.get("csv_num_participants"),
        "video_id_filter":        track.provenance.get("csv_video_id_filter"),
        "video_ids_mixed":        None,
    }


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
            "input_fov_deg": effective_fov,
            "effective_vertical_fov_deg": effective_fov,
        }

    if projection_fov_mode == "horizontal_to_vertical":
        if override_fov_deg is not None:
            horizontal_fov_deg, source = float(override_fov_deg), "override_fov_deg"
        elif "fov_degrees" in cam:
            horizontal_fov_deg, source = float(cam["fov_degrees"]), "json_fov_degrees"
        else:
            horizontal_fov_deg = math.degrees(float(cam["fov_radians"]))
            source = "json_fov_radians"
        effective_fov = horizontal_to_vertical_fov_deg(horizontal_fov_deg, float(vi["aspect_ratio"]))
        return build_projection_matrix_from_fov(
            effective_fov, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]
        ), {
            "projection_fov_mode": "horizontal_to_vertical",
            "projection_fov_source": source,
            "input_fov_deg": horizontal_fov_deg,
            "effective_vertical_fov_deg": effective_fov,
        }

    raise ValueError(f"Unknown projection_fov_mode: {projection_fov_mode}")


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
    projection_fov_mode: str,
) -> tuple[np.ndarray, dict]:
    """Project gaze density onto mesh vertices and return per-vertex saliency."""
    n_verts  = len(mesh.vertices)
    vert_sal = np.zeros(n_verts, dtype=np.float64)

    cam = camera_data["camera_static"]
    frames_list = camera_data["frames"]
    proj_mat, projection_info = resolve_projection_matrix(
        camera_data=camera_data,
        override_fov_deg=override_fov_deg,
        projection_fov_mode=projection_fov_mode,
    )

    view_matrix = np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)

    # Canonical 3DVA pre-transform order: base_rotate_z → recenter → (per-frame ops).
    # bbox_center is taken from ORIGINAL vertices before base_rotate_z so it matches
    # apply_model_transform in the cone/raycast scripts (session-3 bug fix).
    base_verts = np.asarray(mesh.vertices, dtype=np.float64).copy()
    bbox_center = 0.5 * (base_verts.min(axis=0) + base_verts.max(axis=0))
    rz0 = math.radians(base_rotate_z_deg)
    if abs(rz0) > 1e-12:
        cz0, sz0 = math.cos(rz0), math.sin(rz0)
        x0 = cz0 * base_verts[:, 0] - sz0 * base_verts[:, 1]
        y0 = sz0 * base_verts[:, 0] + cz0 * base_verts[:, 1]
        base_verts[:, 0], base_verts[:, 1] = x0, y0
    if recenter_to_bbox_center:
        base_verts -= bbox_center  # uses ORIGINAL bbox_center

    # Camera world position (static for 3DVA: camera never moves, only model rotates).
    camera_world_pos = np.linalg.inv(view_matrix)[:3, 3]

    # Precompute base normals with base_rotate_z already baked in (consistent with
    # base_verts above). Normal transform = rotation only (uniform scale, no translate).
    base_normals = np.asarray(mesh.vertex_normals, dtype=np.float64).copy()
    if abs(rz0) > 1e-12:
        cz0, sz0 = math.cos(rz0), math.sin(rz0)
        nx0 = cz0 * base_normals[:, 0] - sz0 * base_normals[:, 1]
        ny0 = sz0 * base_normals[:, 0] + cz0 * base_normals[:, 1]
        base_normals[:, 0], base_normals[:, 1] = nx0, ny0

    normals_w   = np.empty_like(base_normals)   # reused buffer (avoids per-frame alloc)
    culled_back = 0

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
        # base_rotate_z_deg already applied to base_verts above → pass 0.0 here.
        verts_w = _apply_transform_no_recenter(
            base_verts, camera_data, rot_z,
            0.0, extra_rotate_x_deg, extra_rotate_y_deg,
        )

        screen_xy, w_clip = world_to_screen(verts_w, view_matrix, proj_mat)

        # Back-face culling: rotate normals for this frame (rotation_z only;
        # base_rotate_z already baked into base_normals above).
        normals_w[:, 0] = math.cos(rot_z) * base_normals[:, 0] - math.sin(rot_z) * base_normals[:, 1]
        normals_w[:, 1] = math.sin(rot_z) * base_normals[:, 0] + math.cos(rot_z) * base_normals[:, 1]
        normals_w[:, 2] = base_normals[:, 2]
        rx = math.radians(extra_rotate_x_deg)
        if abs(rx) > 1e-12:
            crx, srx = math.cos(rx), math.sin(rx)
            ny2 = crx * normals_w[:, 1] - srx * normals_w[:, 2]
            nz2 = srx * normals_w[:, 1] + crx * normals_w[:, 2]
            normals_w[:, 1], normals_w[:, 2] = ny2, nz2
        ry = math.radians(extra_rotate_y_deg)
        if abs(ry) > 1e-12:
            cry, sry = math.cos(ry), math.sin(ry)
            nx2 = cry * normals_w[:, 0] + sry * normals_w[:, 2]
            nz2 = -sry * normals_w[:, 0] + cry * normals_w[:, 2]
            normals_w[:, 0], normals_w[:, 2] = nx2, nz2
        to_cam = camera_world_pos[None, :] - verts_w
        front_facing = np.einsum("ij,ij->i", normals_w, to_cam) > 0.0
        culled_back += int((~front_facing).sum())
        screen_xy[(w_clip <= 0) | (~front_facing)] = -1.0

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
        "culled_back_verts":     culled_back,
        **projection_info,
    }
    return vert_sal, stats


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args  = parse_args()
    if args.projection_fov_mode == "json":
        print(
            "[WARN] --projection-fov-mode json для 3DVA даёт НЕВЕРНЫЕ лучи: "
            "JSON projection_matrix кодирует vertical 60° (P[1,1]=1.732), "
            "тогда как физическая камера имеет horizontal 60° → vertical 35.98°. "
            "Используйте --projection-fov-mode horizontal_to_vertical (default).",
            file=sys.stderr,
        )
    paths = resolve_model_paths(args)
    ensure_required_exist(paths)

    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)
    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected a single Trimesh, got {type(mesh)}")

    track = _load_gaze_track(args, paths["json"])
    gaze_batches = track.gaze_batches
    gaze_stats   = _gaze_stats(track)

    tag_parts = [f"sigpx{args.sigma_px}".replace(".", "p")]
    if args.recenter_to_bbox_center:
        tag_parts.append("recenter")
    if abs(args.base_rotate_z_deg) > 1e-12:
        tag_parts.append(f"baserz{args.base_rotate_z_deg}".replace(".", "p"))
    if abs(args.extra_rotate_x_deg) > 1e-12:
        tag_parts.append(f"rotx{args.extra_rotate_x_deg}".replace(".", "p"))
    if abs(args.extra_rotate_y_deg) > 1e-12:
        tag_parts.append(f"roty{args.extra_rotate_y_deg}".replace(".", "p"))
    if args.projection_fov_mode == "json":
        tag_parts.append("fovjson")
    elif args.projection_fov_mode == "horizontal_to_vertical":
        if args.override_fov_deg is None:
            tag_parts.append("fovh2v")
        else:
            tag_parts.append(f"fovh{args.override_fov_deg}_h2v".replace(".", "p"))
    elif args.override_fov_deg is not None:
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
        projection_fov_mode=args.projection_fov_mode,
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
        "gaze_stats":        gaze_stats,
        "participant_input": track.provenance,
        "run_stats":         run_stats,
        "visibility_stats":  vis_stats,
        "method_params": {
            "sigma_px":                args.sigma_px,
            "density_img":             f"{_IMG_W}x{_IMG_H}",
            "deposition":              "bilinear",
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg":       args.base_rotate_z_deg,
            "extra_rotate_x_deg":      args.extra_rotate_x_deg,
            "extra_rotate_y_deg":      args.extra_rotate_y_deg,
            "override_fov_deg":        args.override_fov_deg,
            "projection_fov_mode":     args.projection_fov_mode,
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

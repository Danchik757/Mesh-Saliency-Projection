#!/usr/bin/env python3
"""
Evaluate screen_space_gaussian on one 3DVA model against a pre-built COMBINED GT
(all 3 static views merged into one per-vertex map).

The combined GT is produced by build_3dva_combined_gt.py (scripts/ folder) and
stored as {combined-gt-dir}/{model}_combined_gt.txt — one float per line.

Method (screen_space_gaussian v2):
  1. Accumulate all gaze points into a 2D density image at full 1920×1080 resolution
     using bilinear deposition and convolve with Gaussian sigma = --sigma-px pixels.
     Default sigma = 49 px ≈ 1° of visual angle in the 3DVA paper setup:
       Tobii TX-120, ~90 cm observer-to-screen, 30" Eizo monitor, 1920×1080.
     Formula: 900 mm × tan(1°) × 3.0 px/mm ≈ 47–49 px.
     WARNING: SAL3D uses sigma=26.3px (different setup). Do NOT use 26.3px here.
  2. For each animation frame, transform mesh vertices to world space and project
     them to screen coordinates using the JSON camera matrices.
  3. Sample the gaze density image at each vertex's screen position (bilinear).
  4. Accumulate contributions weighted by the number of gaze points in that frame.

Metrics reported (JSON):
  metrics_vs_gt_combined.screen_space_gaussian.metrics_full:         all vertices
  metrics_vs_gt_combined.screen_space_gaussian.metrics_covered_only: union support of the
      3 source views, where support(view) = visibility OR (GT > 0)
  Use metrics_covered_only for all summary tables.

Bug fixes applied (vs older 3DVA scripts):
  - Resolution: 1920×1080 (was 256×144 in v1).
  - Sigma: --sigma-px in absolute pixels (default 49.0). v1 used sigma_screen=0.05
    (fraction of width) → 12.8 px at 256px = 96 px at 1920px — 3.6× too wide.
  - Bilinear deposition instead of nearest-neighbour.
  - Recenter order: bbox_center from ORIGINAL vertices, computed BEFORE base_rotate_z.
  - FOV: supports the same projection_fov_mode logic as MeshMamba/SAL3D.
    Default mode horizontal_to_vertical treats 3DVA JSON FOV as horizontal 60°
    and converts it to the effective vertical FOV (~35.9834° on 16:9).
  - Transform order for 3DVA:
    base_rotZ → recenter → scale → rotZ_anim → extraX → extraY → translate.

Env vars (used when CLI args are not provided):
  VISUAL_ATTENTION_3D_SHAPES_ROOT  — root of the 3DVA dataset
  THREE_DVA_CSV_ROOT               — directory with per-model CSV gaze files
  THREE_DVA_JSON_ROOT              — directory with per-model JSON camera/animation files
  THREE_DVA_OUTPUT_DIR             — output directory
  THREE_DVA_COMBINED_GT_DIR        — directory with pre-built combined GT files
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

# Default sigma: 49 px at 1920×1080 ≈ 1° visual angle in 3DVA paper setup.
# (Different from SAL3D where sigma=26.3px from a different monitor/distance.)
_DEFAULT_SIGMA_PX = 49.0

FrameGazeBatch = GazeBatch


def _env_path(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var, fallback))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate screen_space_gaussian (v2) on one 3DVA model "
            "against a pre-built combined GT (all 3 views merged). "
            f"Uses full {_IMG_W}×{_IMG_H} density image and sigma in absolute pixels."
        )
    )
    parser.add_argument("--model", default="bunny", help="3DVA model name, e.g. bunny or A380.")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_env_path("VISUAL_ATTENTION_3D_SHAPES_ROOT", "e.g. /srv/datasets/3DVA"),
        help="Root of the 3DVA dataset (3DModels-Simplif-up subdir is used for OBJ).",
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
        "--combined-gt-dir",
        type=Path,
        default=_env_path("THREE_DVA_COMBINED_GT_DIR", "e.g. /srv/datasets/3DVA/CombinedGT"),
        help=(
            "Directory with pre-built combined GT files produced by "
            "scripts/build_3dva_combined_gt.py. "
            "Must contain {model}_combined_gt.txt for each model."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_env_path(
            "THREE_DVA_OUTPUT_DIR",
            str(REPO_ROOT / "results" / "3dva" / "screen_space_combined"),
        ),
        help="Output directory for saliency maps and the evaluation report.",
    )
    parser.add_argument(
        "--sigma-px",
        type=float,
        default=_DEFAULT_SIGMA_PX,
        help=(
            f"Gaussian sigma in absolute pixels at {_IMG_W}×{_IMG_H} resolution. "
            f"Default {_DEFAULT_SIGMA_PX} px ≈ 1° visual angle, 3DVA paper setup. "
            f"v1 bug: sigma_screen=0.05 → 12.8 px @ 256px = 96 px @ 1920px (3.6× too wide). "
            f"SAL3D uses 26.3 px — do NOT use that value here."
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
            "Optional FOV override in degrees. Interpretation depends on "
            "--projection-fov-mode."
        ),
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
        "--video-id",
        type=int,
        default=None,
        help="Optional filter for mixed-session CSVs. A380 requires --video-id 2365.",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Output sub-directory tag. Auto-derived from sigma and transform params if omitted.",
    )
    return parser.parse_args()


# ── file resolution helpers ──────────────────────────────────────────────────

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


def _load_combined_gt(combined_gt_dir: Path, model: str) -> np.ndarray:
    """Load combined GT file. Raises FileNotFoundError if not found."""
    for name in _candidate_model_names(model):
        path = combined_gt_dir / f"{name}_combined_gt.txt"
        if path.is_file():
            return np.loadtxt(str(path), dtype=np.float64)
    raise FileNotFoundError(
        f"Combined GT not found for model '{model}' in {combined_gt_dir}. "
        f"Run scripts/build_3dva_combined_gt.py first."
    )


def _resolve_gt_file(dataset_root: Path, model: str, view: str) -> Path | None:
    candidate_names = [f"{name}_{view}norm" for name in _candidate_model_names(model)]
    return _resolve_casefold_file(dataset_root / "FixationMaps", candidate_names, ".txt")


def _resolve_visibility_file(dataset_root: Path, model: str, view: str) -> Path | None:
    candidate_names = [f"{name}_{view}_visibility" for name in _candidate_model_names(model)]
    return _resolve_casefold_file(dataset_root / "CentricityAndVisibilityMaps", candidate_names, ".txt")


def _load_combined_support_mask(dataset_root: Path, model: str, n_expected: int) -> tuple[np.ndarray, dict]:
    support = np.zeros(n_expected, dtype=bool)
    per_view_counts: dict[str, int] = {}
    warnings: list[str] = []

    for view in ("300", "413", "599"):
        gt_path = _resolve_gt_file(dataset_root, model, view)
        if gt_path is None:
            warnings.append(f"missing GT file for view {view}")
            continue
        gt = np.loadtxt(str(gt_path), dtype=np.float64).reshape(-1)

        vis_path = _resolve_visibility_file(dataset_root, model, view)
        if vis_path is None:
            vis = np.zeros_like(gt, dtype=bool)
            warnings.append(f"missing visibility file for view {view}; using gt>0 only")
        else:
            vis = np.loadtxt(str(vis_path), dtype=np.float64).astype(bool).reshape(-1)

        n = min(n_expected, len(gt), len(vis))
        if len(gt) != len(vis):
            warnings.append(
                f"view {view} length mismatch: gt={len(gt)} vis={len(vis)}; using first {n} entries"
            )

        view_support = vis[:n] | (gt[:n] > 0)
        support[:n] |= view_support
        per_view_counts[view] = int(view_support.sum())

    return support, {"per_view_support_counts": per_view_counts, "warnings": warnings}


def resolve_model_paths(args: argparse.Namespace) -> dict[str, Path]:
    candidate_names = _candidate_model_names(args.model)
    obj_path = _resolve_casefold_file(args.dataset_root / "3DModels-Simplif-up", candidate_names, ".obj")
    if obj_path is None:
        raise FileNotFoundError(
            f"OBJ file not found for model '{args.model}' in "
            f"{args.dataset_root / '3DModels-Simplif-up'}"
        )
    return {
        "json": _resolve_3dva_prefixed_json(args.json_root, args.model),
        "obj":  obj_path,
    }


def ensure_exists(paths: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))


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
    """Apply base_rotZ → scale → rotZ_anim → rotX → rotY → translate (no recentering).

    Vertex recentering is applied once outside the per-frame loop in run_screen_space(),
    so we only apply the per-frame rotation/scale/translate here.

    IMPORTANT: 3DVA transform order matches the render script (3dva_render_1.py).
    Projection FOV is resolved once per run via resolve_projection_matrix().
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
    ones  = np.ones((len(points_w), 1), dtype=np.float64)
    pts_h = np.hstack([points_w, ones])
    cam   = (view_matrix @ pts_h.T).T
    clip  = (proj_mat @ cam.T).T
    w = clip[:, 3]
    safe_w = np.where(np.abs(w) > 1e-12, w, 1e-12)
    ndc_x  = clip[:, 0] / safe_w
    ndc_y  = clip[:, 1] / safe_w
    screen_x = (ndc_x + 1.0) * 0.5
    screen_y = (1.0 - ndc_y) * 0.5
    return np.stack([screen_x, screen_y], axis=1), w


def bilinear_deposit(hist: np.ndarray, x_norm: np.ndarray, y_norm: np.ndarray) -> None:
    """Deposit gaze points into hist using bilinear interpolation (in-place).

    Bilinear deposition distributes each fixation point across the 4 surrounding
    pixels proportionally, avoiding the aliasing of nearest-neighbour (v1 bug).
    """
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
    oob = (
        (screen_xy[:, 0] < 0) | (screen_xy[:, 0] > 1) |
        (screen_xy[:, 1] < 0) | (screen_xy[:, 1] > 1)
    )
    val[oob] = 0.0
    return val


# ── metrics ──────────────────────────────────────────────────────────────────

def _normalize_sum(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    total  = float(values.sum())
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
    saliency_map  = np.asarray(saliency_map,  dtype=np.float64)
    fixation_mask = np.asarray(fixation_mask, dtype=bool)
    if fixation_mask.sum() == 0:
        return 0.0
    std = float(saliency_map.std())
    if std == 0.0:
        return 0.0
    return float(((saliency_map - saliency_map.mean()) / std)[fixation_mask].mean())


def _auc_judd(saliency_map: np.ndarray, fixation_mask: np.ndarray) -> float:
    saliency_map  = _normalize_minmax(saliency_map).reshape(-1)
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
    n_verts  = len(mesh.vertices)
    vert_sal = np.zeros(n_verts, dtype=np.float64)

    cam         = camera_data["camera_static"]
    vi          = camera_data["video_info"]
    frames_list = camera_data["frames"]

    proj_mat, projection_info = resolve_projection_matrix(
        camera_data,
        override_fov_deg=override_fov_deg,
        projection_fov_mode=projection_fov_mode,
    )

    view_matrix = np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)

    # Precompute vertex positions once using the canonical 3DVA order:
    # base_rotate_z -> recenter.
    # bbox_center is computed from ORIGINAL vertices BEFORE base_rotate_z.
    base_verts = np.asarray(mesh.vertices, dtype=np.float64).copy()
    bbox_center = 0.5 * (
        np.asarray(mesh.vertices, dtype=np.float64).min(axis=0)
        + np.asarray(mesh.vertices, dtype=np.float64).max(axis=0)
    )
    rz0 = math.radians(base_rotate_z_deg)
    if abs(rz0) > 1e-12:
        cz0, sz0 = math.cos(rz0), math.sin(rz0)
        x0 = cz0 * base_verts[:, 0] - sz0 * base_verts[:, 1]
        y0 = sz0 * base_verts[:, 0] + cz0 * base_verts[:, 1]
        base_verts[:, 0], base_verts[:, 1] = x0, y0
    if recenter_to_bbox_center:
        base_verts -= bbox_center

    # Camera world position (static for 3DVA: camera never moves, only model rotates).
    camera_world_pos = np.linalg.inv(view_matrix)[:3, 3]

    # Precompute base normals with base_rotate_z already baked in.
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
        rot_z   = float(frames_list[frame]["rotation_z_radians"])
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
        "total_gaze_points":  total_points,
        "frames_used":        frames_used,
        "density_img_shape":  [_IMG_H, _IMG_W],
        "sigma_px":           sigma_px,
        **projection_info,
        "nonzero_vertices":   int(np.count_nonzero(vert_sal)),
        "deposition":         "bilinear",
        "culled_back_verts":  culled_back,
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
    ensure_exists(paths)

    if not args.combined_gt_dir.is_dir():
        raise SystemExit(
            f"--combined-gt-dir not found: {args.combined_gt_dir}\n"
            "Run scripts/build_3dva_combined_gt.py first."
        )

    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)

    # Load OBJ with process=False (required for models like turbine where vertex
    # count may differ from GT line count).
    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected a single Trimesh, got {type(mesh)}")

    # Load combined GT
    combined_gt  = _load_combined_gt(args.combined_gt_dir, args.model)
    n_mesh_verts = len(mesh.vertices)
    n_gt_lines   = len(combined_gt)

    if n_mesh_verts != n_gt_lines:
        print(
            f"[warn] mesh has {n_mesh_verts} vertices but combined GT has {n_gt_lines} lines. "
            "Metrics will use GT length. Expected for 'turbine' (OBJ=20000, GT=19999).",
            file=sys.stderr,
        )

    n_eval = min(n_mesh_verts, n_gt_lines)

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
        tag_parts.append(
            "fovh2v"
            if args.override_fov_deg is None
            else f"fovh{args.override_fov_deg}_h2v".replace(".", "p")
        )
    elif args.override_fov_deg is not None:
        tag_parts.append(f"fov{args.override_fov_deg}".replace(".", "p"))
    tag_parts.append("combined")
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

    # Compute metrics vs combined GT:
    # - full: all vertices
    # - covered_only: union support of source views, where support(view)=visibility OR (GT>0)
    gt_for_metrics = combined_gt[:n_eval]
    pred_for_metrics = vert_sal[:n_eval]
    covered_mask, covered_stats = _load_combined_support_mask(args.dataset_root, args.model, n_eval)
    n_covered = int(covered_mask.sum())
    n_gt_positive = int((gt_for_metrics > 0).sum())

    metrics_vs_gt_combined = {
        "screen_space_gaussian": {
            "metrics_full":         compute_metrics(pred_for_metrics, gt_for_metrics),
            "metrics_covered_only": compute_metrics(
                pred_for_metrics[covered_mask], gt_for_metrics[covered_mask]
            ),
        }
    }

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_screen_space_combined_vertices.txt", vert_sal, fmt="%.10f")

    report = {
        "model":        args.model,
        "tag":          tag,
        "dataset":      "3DVA",
        "script":       "eval_3dva_screen_space_combined",
        "script_version": "v2",
        "n_vertices":            n_mesh_verts,
        "n_gt_lines":            n_gt_lines,
        "n_eval":                n_eval,
        "n_combined_nonzero":    n_gt_positive,
        "n_gt_positive_vertices": n_gt_positive,
        "combined_positive_pct": round(100.0 * n_gt_positive / n_eval, 2) if n_eval else 0.0,
        "n_covered_vertices":    n_covered,
        "covered_support_pct":   round(100.0 * n_covered / n_eval, 2) if n_eval else 0.0,
        "combined_coverage_pct": round(100.0 * n_covered / n_eval, 2) if n_eval else 0.0,
        "gaze_stats":        gaze_stats,
        "participant_input": track.provenance,
        "run_stats":         run_stats,
        "covered_support_stats": covered_stats,
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
                "base_rotate_z → recenter → scale → rotation_z_anim "
                "→ extra_rotate_x → extra_rotate_y → translation"
            ),
        },
        "metrics_note": (
            "metrics_covered_only: union support of the 3 source views, "
            "where support(view)=visibility OR (GT > 0). "
            "This is the valid benchmark domain — use for all summary tables. "
            "metrics_full: all mesh vertices (includes unobserved back-faces, lower CC expected). "
            f"Sigma {args.sigma_px}px at {_IMG_W}px ≈ 1° visual angle (3DVA paper setup). "
            "SAL3D uses 26.3px — different setup, do not mix."
        ),
        "metrics_vs_gt_combined": metrics_vs_gt_combined,
    }

    report_path = out_dir / f"{args.model}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}", flush=True)


if __name__ == "__main__":
    main()

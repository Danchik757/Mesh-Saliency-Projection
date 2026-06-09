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
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.stats import pearsonr, spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.participant_loader import GazeBatch, load_processed_track, load_csv_compat_track  # noqa: E402

WIDTH = 1920
HEIGHT = 1080

FrameGazeBatch = GazeBatch


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
        help="Directory with per-model 3DVA CSV gaze files (only used with --csv-compat).",
    )
    parser.add_argument(
        "--fixation-root",
        type=Path,
        default=Path(os.environ["FIXATION_ROOT"]) if "FIXATION_ROOT" in os.environ else None,
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
        help="Output sub-directory tag. Auto-derived from transform params if omitted.",
    )
    return parser.parse_args()


def _candidate_model_names(model: str) -> list[str]:
    raw = model.strip()
    variants = [raw, raw.lower(), raw.upper()]
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
    """Return the visibility file for (model, view) or None if not present."""
    candidate_names = [f"{name}_{view}_visibility" for name in _candidate_model_names(model)]
    return _resolve_casefold_file(vis_root, candidate_names, ".txt")


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


def ensure_exists(paths: dict[str, Path | None]) -> None:
    required_keys = ["json", "obj", "gt_300", "gt_413", "gt_599"]
    missing = [f"{name}: {paths[name]}" for name in required_keys
               if paths[name] is None or not paths[name].exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))


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
    # Canonical order (matches render_preview_from_manifest.py):
    #   bbox_center computed from ORIGINAL vertices, before any rotation.
    bbox_center = 0.5 * (v.min(axis=0) + v.max(axis=0))
    rz0 = math.radians(base_rotate_z_deg)
    if abs(rz0) > 1e-12:
        cz0, sz0 = math.cos(rz0), math.sin(rz0)
        x0 = cz0 * v[:, 0] - sz0 * v[:, 1]
        y0 = sz0 * v[:, 0] + cz0 * v[:, 1]
        v[:, 0], v[:, 1] = x0, y0
    if recenter_to_bbox_center:
        v -= bbox_center

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


# ── metric helpers ──────────────────────────────────────────────────────────

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
) -> tuple[np.ndarray, np.ndarray, dict]:
    n_verts = len(mesh.vertices)
    raycast_counts = np.zeros(n_verts, dtype=np.float64)
    cone_counts    = np.zeros(n_verts, dtype=np.float64)

    proj_mat, projection_info = resolve_projection_matrix(
        camera_data=camera_data,
        override_fov_deg=override_fov_deg,
        projection_fov_mode=projection_fov_mode,
    )

    total_points = total_hits = total_cone_v = 0

    frames_list = camera_data["frames"]
    for frame, batch in gaze_batches.items():
        if batch.x_norm.size == 0:
            continue
        if frame >= len(frames_list):
            continue
        rot_z = float(frames_list[frame]["rotation_z_radians"])

        verts_t = apply_model_transform(
            mesh.vertices,
            camera_data,
            rot_z,
            recenter_to_bbox_center,
            base_rotate_z_deg,
            extra_rotate_x_deg,
            extra_rotate_y_deg,
        )
        # Avoid deep mesh.copy() — create a lightweight Trimesh with new vertices only.
        xmesh = trimesh.Trimesh(vertices=verts_t, faces=mesh.faces, process=False)

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
        tri_coords = verts_t[tri_verts]
        dists = np.linalg.norm(tri_coords - hit_pts[:, None, :], axis=2)
        nearest_local = np.argmin(dists, axis=1)
        nearest_v = tri_verts[np.arange(len(tri_verts)), nearest_local]
        np.add.at(raycast_counts, nearest_v, 1.0)

        # cone_gaussian_on_mesh — build KD-tree once per frame on transformed vertices.
        vtree = cKDTree(verts_t)
        origins_at_hit = origins[ray_idx]
        depth = np.linalg.norm(hit_pts - origins_at_hit, axis=1)
        sigma_world = np.maximum(depth * math.tan(math.radians(sigma_deg)), 1e-6)
        # Each hit has a depth-dependent sigma, so its support radius must remain
        # point-specific. A shared median radius changes the cone method.
        for pt, sigma in zip(hit_pts, sigma_world):
            idxs = vtree.query_ball_point(pt, r=radius_sigma_mult * sigma)
            if not idxs:
                idxs = [int(vtree.query(pt)[1])]
            idx_arr = np.asarray(idxs, dtype=np.int64)
            lv = verts_t[idx_arr]
            w  = np.exp(-0.5 * np.sum((lv - pt) ** 2, axis=1) / sigma ** 2)
            cone_counts[idx_arr] += w
            total_cone_v += len(idxs)

        total_hits += len(hit_pts)

    stats = {
        "total_gaze_points":  total_points,
        "successful_hits":    total_hits,
        "hit_rate":           total_hits / total_points if total_points else 0.0,
        "raycast_nonzero_vertices": int(np.count_nonzero(raycast_counts)),
        "cone_nonzero_vertices":    int(np.count_nonzero(cone_counts)),
        **projection_info,
    }
    return raycast_counts, cone_counts, stats


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

    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)
    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected a single Trimesh, got {type(mesh)}")

    track = _load_gaze_track(args, paths["json"])
    gaze_batches = track.gaze_batches
    gaze_stats   = _gaze_stats(track)

    tag_parts = []
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
    )

    raycast_fix = scale_like_fixation_map(raycast)
    cone_fix    = scale_like_fixation_map(cone)

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_raycast_norm.txt", raycast_fix, fmt="%.10f")
    np.savetxt(out_dir / f"{args.model}_cone_norm.txt",    cone_fix,    fmt="%.10f")

    # Build metrics with and without visibility masking for each view.
    results: dict[str, dict] = {
        "raycast_nearest_vertex": {},
        "cone_gaussian_on_mesh": {},
    }
    vis_stats: dict[str, dict] = {}
    for view in ("300", "413", "599"):
        gt = np.loadtxt(paths[f"gt_{view}"])
        # full-mesh metrics
        results["raycast_nearest_vertex"][view] = {
            "metrics_vs_gt_full": compute_metrics(raycast_fix, gt),
            "metrics_vs_gt_visible_only": None,
        }
        results["cone_gaussian_on_mesh"][view] = {
            "metrics_vs_gt_full": compute_metrics(cone_fix, gt),
            "metrics_vs_gt_visible_only": None,
        }
        # visibility-masked metrics
        vis_path = paths.get(f"vis_{view}")
        if vis_path is not None and vis_path.exists():
            vis = np.loadtxt(vis_path).astype(bool)
            if len(vis) == len(mesh.vertices):
                results["raycast_nearest_vertex"][view]["metrics_vs_gt_visible_only"] = \
                    compute_metrics(raycast_fix[vis], gt[vis])
                results["cone_gaussian_on_mesh"][view]["metrics_vs_gt_visible_only"] = \
                    compute_metrics(cone_fix[vis], gt[vis])
                vis_stats[view] = {"n_visible": int(vis.sum()), "n_total": int(len(vis))}
            else:
                print(f"[warn] visibility length mismatch for view {view}, skipping", flush=True)
        else:
            print(f"[warn] no visibility file for view {view}", flush=True)

    report = {
        "model":   args.model,
        "tag":     tag,
        "dataset": "3DVA",
        "gaze_stats":        gaze_stats,
        "participant_input": track.provenance,
        "run_stats":         run_stats,
        "visibility_stats":  vis_stats,
        "method_params": {
            "sigma_deg":              args.sigma_deg,
            "radius_sigma_mult":      args.radius_sigma_mult,
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg":      args.base_rotate_z_deg,
            "extra_rotate_x_deg":     args.extra_rotate_x_deg,
            "extra_rotate_y_deg":     args.extra_rotate_y_deg,
            "override_fov_deg":       args.override_fov_deg,
            "projection_fov_mode":    args.projection_fov_mode,
            "video_id":               args.video_id,
            "transform_order": "base_rotate_z -> recenter -> scale -> rotation_z -> extra_rotate_x -> extra_rotate_y -> translation",
        },
        "metrics_note": (
            "metrics_vs_gt_full: all mesh vertices. "
            "metrics_vs_gt_visible_only: restricted to vertices visible from each GT static view "
            "(CentricityAndVisibilityMaps/*.visibility.txt); matches 3DVA paper protocol (Section 5.2)."
        ),
        "metrics_vs_gt": results,
    }

    report_path = out_dir / f"{args.model}_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()

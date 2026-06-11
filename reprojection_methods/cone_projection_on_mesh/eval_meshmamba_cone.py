#!/usr/bin/env python3
"""
Evaluate two face-level gaze-to-mesh transfer methods on one MeshMamba non_texture model.

Methods:
1. raycast_nearest_face:
   Cast the gaze ray through each screen point and assign the hit to the
   intersected face (index_tri) directly.
2. cone_gaussian_on_mesh (face-level):
   Same ray hit, but spread its contribution to nearby faces with a Gaussian
   whose world-space sigma is derived from the angular uncertainty.

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

from utils.participant_loader import (  # noqa: E402
    GazeBatch,
    TIMING_CONTRACT_CROPPED_RESET,
    TIMING_CONTRACT_ONE_TURN,
    guard_report_compatible,
    load_csv_compat_track,
    load_processed_track,
)

FrameGazeBatch = GazeBatch


def _env_path(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var, fallback))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate raycast_nearest_face and cone_gaussian_on_mesh on one MeshMamba model."
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
        help="Directory with per-model MeshMamba CSV gaze files (only used with --csv-compat).",
    )
    parser.add_argument(
        "--fixation-root",
        type=Path,
        default=next(
            (Path(os.environ[k]) for k in (
                "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT",
                "MESHMAMBA_PROCESSED_FIXATIONS_ROOT",
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
        "--timing-contract",
        default=os.environ.get("REPROJECT_TIMING_CONTRACT", TIMING_CONTRACT_CROPPED_RESET),
        choices=[TIMING_CONTRACT_CROPPED_RESET, TIMING_CONTRACT_ONE_TURN],
        help=(
            "Timing contract for participant data. "
            "'cropped_reset': skip 1.8s/0.2s (default, offset_2000 data). "
            "'one_turn_from_start': one full rotation from frame 0 (offset_0 data). "
            "Also read from REPROJECT_TIMING_CONTRACT env var."
        ),
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(os.environ.get("REPROJECT_GAZE_DELAY_SECONDS", "0.0")),
        help=(
            "Gaze-to-placement delay in seconds (one_turn_from_start only). "
            "+0.2 → gaze[6:6+N] paired with placement[0:N]. "
            "-0.2 → gaze[0:N] paired with placement[6:6+N]. "
            "Default 0.0. Env: REPROJECT_GAZE_DELAY_SECONDS."
        ),
    )
    parser.add_argument(
        "--frame-offset",
        type=int,
        default=int(os.environ.get("REPROJECT_FRAME_OFFSET", "0")),
        help=(
            "Absolute frame offset for window mode (one_turn_from_start only). "
            "0=cut_tail, tail=cut_head, tail//2=center. "
            "Env: REPROJECT_FRAME_OFFSET."
        ),
    )
    parser.add_argument(
        "--fixation-data-tag",
        default=os.environ.get("REPROJECT_FIXATION_DATA_TAG"),
        help=(
            "Label for the fixation dataset version embedded in provenance "
            "(e.g. 'processed_fixations_offset0_full_cleaned'). "
            "Falls back to basename of --fixation-root. "
            "Env: REPROJECT_FIXATION_DATA_TAG."
        ),
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
            str(REPO_ROOT / "results" / "meshmamba" / "cone_raycast"),
        ),
        help="Output directory for saliency maps and the evaluation report.",
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
        if f.stem.lower().replace("_", "-",).replace(" ", "-") in model_norms:
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
        "json": find_json_file(args.json_root, args.model, texture_type),
        "obj":  obj_path,
        "gt":   gt_path,
    }


def ensure_exists(paths: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))


def _load_gaze_track(args: argparse.Namespace, placement_path: Path):
    texture_type   = args.texture_type
    dataset        = f"MeshMamba_{texture_type}"
    model          = args.model
    canonical_name = f"MeshMamba_{texture_type}_{model}"
    if args.csv_compat:
        return load_csv_compat_track(
            find_csv_file(args.csv_root, model), placement_path,
            dataset=dataset, model=model, canonical_name=canonical_name,
        )
    if args.fixation_root is None:
        raise SystemExit("--fixation-root is required unless --csv-compat is set")
    data_tag = getattr(args, "fixation_data_tag", None) or Path(args.fixation_root).name
    return load_processed_track(
        args.fixation_root / canonical_name / "fixations.json",
        placement_path,
        dataset=dataset, model=model, canonical_name=canonical_name,
        timing_contract=args.timing_contract,
        delay_seconds=getattr(args, "delay_seconds", 0.0),
        frame_offset=getattr(args, "frame_offset", 0),
        fixation_data_tag=data_tag,
    )


def _gaze_stats(track) -> dict:
    return {
        "num_rows":               track.provenance.get("csv_num_rows"),
        "num_participants":       track.provenance.get("csv_num_participants"),
        "num_points":             sum(len(b.x_norm) for b in track.gaze_batches.values()),
        "num_frames_with_points": sum(1 for b in track.gaze_batches.values() if len(b.x_norm) > 0),
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
    for threshold, label in ((0.0, "zero"), (1e-8, "le_1e_8"), (1e-6, "le_1e_6")):
        low_pred = pred_prob <= threshold
        metrics[f"gt_mass_on_pred_{label}"] = float(gt_prob[low_pred].sum())
        metrics[f"pred_mass_on_pred_{label}"] = float(pred_prob[low_pred].sum())
        metrics[f"pred_count_{label}"] = float(low_pred.sum())
    kld_terms = gt_prob_safe * np.log(gt_prob_safe / pred_prob_safe)
    top_k = min(100, kld_terms.size)
    if top_k > 0:
        idx = np.argpartition(kld_terms, -top_k)[-top_k:]
        metrics["top100_kld_contrib_sum"] = float(kld_terms[idx].sum())
        metrics["top100_kld_gt_mass"] = float(gt_prob[idx].sum())
        metrics["top100_kld_pred_mass"] = float(pred_prob[idx].sum())
    else:
        metrics["top100_kld_contrib_sum"] = 0.0
        metrics["top100_kld_gt_mass"] = 0.0
        metrics["top100_kld_pred_mass"] = 0.0

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
    transform_order: str,
) -> tuple[np.ndarray, np.ndarray, dict]:
    n_faces = len(mesh.faces)
    raycast_counts = np.zeros(n_faces, dtype=np.float64)
    cone_counts    = np.zeros(n_faces, dtype=np.float64)

    cam = camera_data["camera_static"]
    vi  = camera_data["video_info"]
    frames_list = camera_data["frames"]

    proj_mat, projection_info = resolve_projection_matrix(
        camera_data,
        override_fov_deg=override_fov_deg,
        projection_fov_mode=projection_fov_mode,
    )

    total_points = total_hits = total_cone_f = 0

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
            transform_order,
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

        # raycast_nearest_face — accumulate directly on the hit face
        np.add.at(raycast_counts, tri_idx, 1.0)

        # cone_gaussian_on_mesh (face-level) — spread to nearby face centroids
        face_centroids_w = np.asarray(xmesh.triangles_center, dtype=np.float64)
        ftree = cKDTree(face_centroids_w)
        origins_at_hit = origins[ray_idx]
        depth = np.linalg.norm(hit_pts - origins_at_hit, axis=1)
        sigma_world = np.maximum(depth * math.tan(math.radians(sigma_deg)), 1e-6)
        for pt, sigma in zip(hit_pts, sigma_world):
            idxs = ftree.query_ball_point(pt, r=radius_sigma_mult * sigma) or [int(ftree.query(pt)[1])]
            lf = face_centroids_w[np.asarray(idxs, dtype=np.int64)]
            w  = np.exp(-0.5 * np.sum((lf - pt) ** 2, axis=1) / sigma ** 2)
            cone_counts[np.asarray(idxs, dtype=np.int64)] += w
            total_cone_f += len(idxs)

        total_hits += len(hit_pts)

    stats = {
        "total_gaze_points":   total_points,
        "successful_hits":     total_hits,
        "hit_rate":            total_hits / total_points if total_points else 0.0,
        "raycast_nonzero_faces": int(np.count_nonzero(raycast_counts)),
        "cone_nonzero_faces":    int(np.count_nonzero(cone_counts)),
        "projection": projection_info,
    }
    return raycast_counts, cone_counts, stats


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
    if args.override_fov_deg is not None:
        tag_parts.append(f"fov{args.override_fov_deg}".replace(".", "p"))
    if args.projection_fov_mode != "vertical":
        tag_parts.append(args.projection_fov_mode.replace("_", ""))
    if args.transform_order != "eval":
        tag_parts.append(args.transform_order)
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

    gt = np.loadtxt(paths["gt"])
    if len(gt) != len(mesh.faces):
        raise SystemExit(
            f"GT face count mismatch: GT has {len(gt)} entries, mesh has {len(mesh.faces)} faces."
        )

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_raycast_faces.txt", raycast, fmt="%.10f")
    np.savetxt(out_dir / f"{args.model}_cone_faces.txt",    cone,    fmt="%.10f")

    results = {
        "raycast_nearest_face":   compute_metrics(raycast, gt),
        "cone_gaussian_on_mesh":  compute_metrics(cone,    gt),
    }

    report = {
        "model":   args.model,
        "tag":     tag,
        "dataset": f"MeshMamba_{args.texture_type}",
        "gt_file": str(paths["gt"].name),
        "n_faces": int(len(mesh.faces)),
        "gaze_stats":        gaze_stats,
        "participant_input": track.provenance,
        "run_stats":         run_stats,
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
    guard_report_compatible(
        report_path,
        timing_contract=getattr(args, "timing_contract", TIMING_CONTRACT_CROPPED_RESET),
        fixation_data_tag=track.provenance.get("fixation_data_tag"),
        delay_frames=track.provenance.get("delay_frames"),
        turn_frame_count=track.provenance.get("turn_frame_count"),
        gaze_start_frame=track.provenance.get("gaze_start_frame"),
        placement_start_frame=track.provenance.get("placement_start_frame"),
        frame_offset=track.provenance.get("frame_offset", 0),
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()

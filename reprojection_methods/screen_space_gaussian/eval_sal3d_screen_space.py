#!/usr/bin/env python3
"""
Evaluate screen_space_gaussian on one SAL3D model.

Method (screen_space_gaussian):
  1. Accumulate all gaze points into a per-frame 2D density image (Gaussian-blurred).
  2. For each animation frame that has gaze data, transform mesh VERTICES to world
     space and project them to screen coordinates.
  3. Back-face cull vertices whose normal points away from the camera.
  4. Sample the per-frame gaze density image at each visible vertex's screen position.
  5. Accumulate contributions weighted by the number of gaze points in that frame.
  6. Compare the resulting per-vertex saliency map against per-vertex GT from Gaze/*.txt.

GT granularity: per-vertex (Gaze/<model>.txt, 20K rows × 8 cols, col 6 = fixation_density).
Two metric sections are reported:
  metrics_vs_gt_full_mesh    — all OBJ vertices (valid only for direct-match 20K models)
  metrics_vs_gt_covered_only — only vertices covered by GT (valid for ALL models)

Transform recipe (validated, Blender IoU ≥ 0.977 across all 57 SAL3D models):
  forward_axis='Z', up_axis='Y' → implicit Rx(90°)
  --recenter-to-bbox-center  --extra-rotate-x-deg 90.0
  --projection-fov-mode horizontal_to_vertical
  --transform-order blender_rig

JSON prefix:  Sal3D_<model>.json
OBJ path:     {dataset_root}/Meshes/<model>.obj
GT path:      {dataset_root}/Gaze/<model>.txt

Env vars:
  SAL3D_DATASET_ROOT   — root containing Gaze/, Meshes/, Smooth_Gaze/
  SAL3D_CSV_ROOT       — directory with per-model CSV gaze files (our participants)
  SAL3D_JSON_ROOT      — directory with per-model Sal3D_<model>.json files
  SAL3D_OUTPUT_DIR     — output directory
  SAL3D_SMOOTH_GAZE_DIR — directory with <model>_neighbors.txt for GT smoothing
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
from utils.sal3d_fixed_gt import load_fixed_face_gt  # noqa: E402

_IMG_W = 1920
_IMG_H = 1080

FrameGazeBatch = GazeBatch


def _env_path(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var, fallback))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate screen_space_gaussian on one SAL3D model."
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
        help="Directory with per-model SAL3D CSV gaze files (only used with --csv-compat).",
    )
    parser.add_argument(
        "--fixation-root",
        type=Path,
        default=next(
            (Path(os.environ[k]) for k in (
                "FIXATION_ROOT", "REPROJECT_PROCESSED_FIXATIONS_ROOT",
                "SAL3D_PROCESSED_FIXATIONS_ROOT",
            ) if k in os.environ),
            None,
        ),
        help="Root of the processed fixation JSON tree (offset0 full cleaned for rc3+). Required unless --csv-compat is set.",
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
        default=_env_path("SAL3D_JSON_ROOT", "e.g. /srv/side_inputs/SAL3D/json"),
        help="Directory with per-model Sal3D_<model>.json camera/animation files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_env_path(
            "SAL3D_OUTPUT_DIR",
            str(REPO_ROOT / "results" / "sal3d" / "screen_space_gaussian"),
        ),
        help="Output directory for saliency maps and the evaluation report.",
    )
    parser.add_argument(
        "--gt-column",
        type=int,
        default=6,
        choices=[6, 7],
        help="Column index in Gaze/*.txt to use as GT: 6=fixation_density (default), 7=binary.",
    )
    parser.add_argument(
        "--smooth-gaze-dir",
        type=Path,
        default=_env_path("SAL3D_SMOOTH_GAZE_DIR", ""),
        help=(
            "Directory with <model>_neighbors.txt files (SAL3D_final/Smooth Gaze/). "
            "When provided, the raw fixation density is propagated to neighbours "
            "using the algorithm from the original paper before metric computation."
        ),
    )
    parser.add_argument(
        "--smooth-ratio",
        type=int,
        default=500,
        help="Max number of neighbours to propagate to per fixated vertex (paper default: 500).",
    )
    parser.add_argument(
        "--sigma-px",
        type=float,
        default=26.3,
        help="Gaussian sigma in absolute pixels of the density image (default 26.3 px at 1920×1080).",
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
    parser.add_argument(
        "--fixed-gt-dir",
        type=Path,
        default=next(
            (Path(os.environ[k]) for k in ("SAL3D_FIXED_GT_DIR",) if k in os.environ),
            None,
        ),
        help=(
            "Directory with <model>_faces.txt per-face fixed GT files "
            "(sal3d_fixed_face_gt/). When provided, metrics_vs_fixed_face_gt is "
            "added to the report using face-domain predictions."
        ),
    )
    parser.add_argument(
        "--sal3d-manifest",
        type=Path,
        default=None,
        help="Path to sal3d_manifest.csv (optional, recorded in provenance).",
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


def resolve_model_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    names = _candidate_model_names(args.model)

    obj_path = _resolve(args.dataset_root / "Meshes", names, ".obj")
    if obj_path is None:
        raise FileNotFoundError(
            f"OBJ not found for '{args.model}' in {args.dataset_root / 'Meshes'}"
        )

    gt_path = _resolve(args.dataset_root / "Gaze", names, ".txt")
    fixed_gt_dir = getattr(args, "fixed_gt_dir", None)
    if gt_path is None and not (fixed_gt_dir and Path(str(fixed_gt_dir)).is_dir()):
        raise FileNotFoundError(
            f"Gaze GT not found for '{args.model}' in {args.dataset_root / 'Gaze'}"
        )

    json_names = [f"Sal3D_{n}" for n in names]
    json_path = _resolve(args.json_root, json_names, ".json")
    if json_path is None:
        raise FileNotFoundError(
            f"JSON not found for '{args.model}' (prefix Sal3D_) in {args.json_root}"
        )

    return {"obj": obj_path, "gt": gt_path, "json": json_path}


def ensure_exists(paths: dict[str, Path | None]) -> None:
    missing = [f"{k}: {v}" for k, v in paths.items() if v is not None and not v.exists()]
    if missing:
        raise SystemExit("Missing inputs:\n" + "\n".join(missing))


# ── Smooth Gaze loading and GT smoothing ─────────────────────────────────────

def load_smooth_gaze(smooth_gaze_dir: Path, model: str) -> dict[int, list[int]] | None:
    """Load <model>_neighbors.txt from SAL3D_final/Smooth Gaze/."""
    if not smooth_gaze_dir or not Path(smooth_gaze_dir).is_dir():
        return None

    candidates = _candidate_model_names(model)
    for name in candidates:
        path = Path(smooth_gaze_dir) / f"{name}_neighbors.txt"
        if path.exists():
            break
    else:
        return None

    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    ids: list[int] = []
    neighbor_lists: list[list[int]] = []

    ids.append(int(lines[0].replace(" neighbors", "").strip()))
    for line in lines[1:]:
        parts = line.strip().split(";")
        if "neighbors" in line:
            neighbor_lists.append([int(x) for x in parts[:-1]])
            next_id = parts[-1].replace(" neighbors", "").strip()
            ids.append(int(next_id))
        else:
            neighbor_lists.append([int(x) for x in parts if x])

    return {vid: nbrs for vid, nbrs in zip(ids, neighbor_lists)}


def apply_gt_smoothing(
    raw_gt: np.ndarray,
    smooth_gaze: dict[int, list[int]],
    ratio: int = 500,
) -> np.ndarray:
    """Propagate raw fixation density to neighbouring vertices (SAL3D paper algorithm)."""
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
    gaze_txt: Path,
    mesh_vertices: np.ndarray,
    gt_column: int,
    smooth_gaze: dict[int, list[int]] | None = None,
    smooth_ratio: int = 500,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Load GT saliency from Gaze/*.txt, optionally smooth, then align to OBJ vertices.

    Returns:
        gt:       (N_vertices,) aligned to OBJ vertex order; uncovered → 0.
        gt_mask:  (N_vertices,) bool — True for vertices with GT coverage.
        smoothed: True if GT smoothing was applied.
    """
    data = np.loadtxt(gaze_txt)
    gaze_xyz = data[:, :3]
    raw_sal  = data[:, gt_column].astype(np.float64)

    n_verts = len(mesh_vertices)
    n_gaze  = len(gaze_xyz)

    if n_gaze > n_verts:
        raise ValueError(
            f"GT row count ({n_gaze}) > OBJ vertex count ({n_verts}). "
            "Cannot align GT to mesh."
        )

    if smooth_gaze is not None and gt_column != 7:
        gaze_sal = apply_gt_smoothing(raw_sal, smooth_gaze, ratio=smooth_ratio)
        smoothed = True
    else:
        gaze_sal = raw_sal
        smoothed = False

    tree = cKDTree(mesh_vertices)
    dists, idxs = tree.query(gaze_xyz, k=1)
    if dists.max() > 1e-4:
        raise ValueError(
            f"GT vertex mismatch: max nearest-neighbor dist = {dists.max():.6f} "
            "(expected 0 — GT and OBJ may be different meshes)"
        )

    gt = np.zeros(n_verts, dtype=np.float64)
    gt[idxs] = gaze_sal
    gt_mask = np.zeros(n_verts, dtype=bool)
    gt_mask[idxs] = True
    return gt, gt_mask, smoothed


# ── gaze loading ──────────────────────────────────────────────────────────────

def _load_gaze_track(args: argparse.Namespace, placement_path: Path):
    dataset        = "SAL3D"
    model          = args.model
    canonical_name = f"SAL3D_{model}"
    if args.csv_compat:
        names    = _candidate_model_names(model)
        csv_path = _resolve(args.csv_root, names, ".csv")
        if csv_path is None:
            raise FileNotFoundError(f"CSV not found for '{model}' in {args.csv_root}")
        return load_csv_compat_track(
            csv_path, placement_path,
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


# ── view / projection ─────────────────────────────────────────────────────────

def get_view_matrix(camera_data: dict) -> np.ndarray:
    """Return 4×4 view matrix.

    SAL3D JSONs store rotation_euler_radians + location instead of view_matrix.
    """
    cam = camera_data["camera_static"]
    if "view_matrix" in cam:
        return np.asarray(cam["view_matrix"], dtype=np.float64).reshape(4, 4)

    rx_a, ry_a, rz_a = [float(a) for a in cam["rotation_euler_radians"]]

    def Rx(a: float) -> np.ndarray:
        return np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])

    def Ry(a: float) -> np.ndarray:
        return np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])

    def Rz(a: float) -> np.ndarray:
        return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])

    R = Rz(rz_a) @ Ry(ry_a) @ Rx(rx_a)
    loc = np.array([float(x) for x in cam["location"]])
    cam_world = np.eye(4)
    cam_world[:3, :3] = R
    cam_world[:3, 3] = loc
    return np.linalg.inv(cam_world)


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
            h_fov, src = float(override_fov_deg), "override_fov_deg"
        elif "fov_degrees" in cam:
            h_fov, src = float(cam["fov_degrees"]), "json_fov_degrees"
        else:
            h_fov, src = math.degrees(float(cam["fov_radians"])), "json_fov_radians"
        eff = horizontal_to_vertical_fov_deg(h_fov, float(vi["aspect_ratio"]))
        return build_projection_matrix_from_fov(eff, vi["aspect_ratio"], cam["clip_start"], cam["clip_end"]), {
            "projection_fov_mode": "horizontal_to_vertical",
            "input_fov_deg": h_fov,
            "effective_vertical_fov_deg": eff,
            "fov_source": src,
        }

    raise ValueError(f"Unknown projection_fov_mode: {mode}")


# ── mesh transform ─────────────────────────────────────────────────────────────

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
        v *= scale
        v = rx(v, extra_rotate_x_deg)
        v = ry(v, extra_rotate_y_deg)
        v = rz(v, base_z_rad)
        v = rz(v, rotation_z_rad)
    elif transform_order == "eval":
        v = rz(v, base_z_rad)
        v *= scale
        v = rz(v, rotation_z_rad)
        v = rx(v, extra_rotate_x_deg)
        v = ry(v, extra_rotate_y_deg)
    else:
        raise ValueError(f"Unknown transform_order: {transform_order}")

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
    """Rotate normals with the same orientation chain as the mesh (no scale/translate)."""
    v = np.asarray(normals, dtype=np.float64).copy()

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

    base_z_rad = math.radians(base_rotate_z_deg)

    if transform_order == "blender_rig":
        v = rx(v, extra_rotate_x_deg)
        v = ry(v, extra_rotate_y_deg)
        v = rz(v, base_z_rad)
        v = rz(v, rotation_z_rad)
    elif transform_order == "eval":
        v = rz(v, base_z_rad)
        v = rz(v, rotation_z_rad)
        v = rx(v, extra_rotate_x_deg)
        v = ry(v, extra_rotate_y_deg)
    else:
        raise ValueError(f"Unknown transform_order: {transform_order}")

    norm = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(norm > 1e-12, norm, 1.0)


# ── screen projection ─────────────────────────────────────────────────────────

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
    ndc_x = clip[:, 0] / safe_w
    ndc_y = clip[:, 1] / safe_w
    screen_x = (ndc_x + 1.0) * 0.5
    screen_y = (1.0 - ndc_y) * 0.5
    return np.stack([screen_x, screen_y], axis=1), w


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


# ── metrics ───────────────────────────────────────────────────────────────────

def _deposit_bilinear_batch(hist: np.ndarray, x: np.ndarray, y: np.ndarray) -> None:
    """Vectorised bilinear deposition of gaze points (weight=1 each) into hist."""
    H, W = hist.shape
    x = np.clip(x.astype(np.float64), 0.0, W - 1.0)
    y = np.clip(y.astype(np.float64), 0.0, H - 1.0)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = np.minimum(x0 + 1, W - 1)
    y1 = np.minimum(y0 + 1, H - 1)
    dx = x - x0
    dy = y - y0
    np.add.at(hist, (y0, x0), (1.0 - dx) * (1.0 - dy))
    np.add.at(hist, (y0, x1), dx * (1.0 - dy))
    np.add.at(hist, (y1, x0), (1.0 - dx) * dy)
    np.add.at(hist, (y1, x1), dx * dy)


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
    lcc, _ = pearsonr(pred, gt)
    spr, _ = spearmanr(pred, gt)
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
    for thr, label in ((0.0, "zero"), (1e-8, "le_1e_8"), (1e-6, "le_1e_6")):
        low_pred = pred_prob <= thr
        m[f"gt_mass_on_pred_{label}"] = float(gt_prob[low_pred].sum())
        m[f"pred_mass_on_pred_{label}"] = float(pred_prob[low_pred].sum())
        m[f"pred_count_{label}"] = float(low_pred.sum())
    kld_terms = (gt_prob + eps) * np.log((gt_prob + eps) / (pred_prob + eps))
    top_k = min(100, kld_terms.size)
    if top_k > 0:
        idx = np.argpartition(kld_terms, -top_k)[-top_k:]
        m["top100_kld_contrib_sum"] = float(kld_terms[idx].sum())
        m["top100_kld_gt_mass"] = float(gt_prob[idx].sum())
        m["top100_kld_pred_mass"] = float(pred_prob[idx].sum())
    else:
        m["top100_kld_contrib_sum"] = 0.0
        m["top100_kld_gt_mass"] = 0.0
        m["top100_kld_pred_mass"] = 0.0
    for pct in proxy_percentiles:
        thr  = float(np.quantile(gt_unit, pct / 100.0))
        mask = gt_unit >= thr
        top  = 100.0 - pct
        lbl  = str(int(round(top))) if math.isclose(top, round(top)) else str(top).replace(".", "p")
        m[f"NSS_gt_top_{lbl}pct_proxy"]      = _nss(pred_unit, mask)
        m[f"AUC_Judd_gt_top_{lbl}pct_proxy"] = _auc_judd(pred_unit, mask)
        m[f"GTMaskCount_top_{lbl}pct_proxy"] = float(mask.sum())
    return m


# ── screen-space evaluation ───────────────────────────────────────────────────

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
    transform_order: str,
) -> tuple[np.ndarray, dict]:
    """Accumulate per-frame screen-space gaze density onto mesh vertices.

    Returns:
        vert_sal: (N_vertices,) per-vertex saliency accumulation.
        stats:    run statistics dict.
    """
    n_verts = len(mesh.vertices)
    vert_sal = np.zeros(n_verts, dtype=np.float64)

    frames_list = camera_data["frames"]
    proj_mat, proj_info = resolve_projection_matrix(
        camera_data, override_fov_deg, projection_fov_mode
    )
    view_matrix = get_view_matrix(camera_data)

    # Pre-compute recentered vertices and vertex normals once.
    base_verts = np.asarray(mesh.vertices, dtype=np.float64).copy()
    base_normals = np.asarray(mesh.vertex_normals, dtype=np.float64).copy()
    if recenter_to_bbox_center:
        bbox_center = 0.5 * (base_verts.min(axis=0) + base_verts.max(axis=0))
        base_verts = base_verts - bbox_center

    camera_world_pos = np.linalg.inv(view_matrix)[:3, 3]
    total_points = 0
    culled_back_verts = 0
    total_weight = 0.0
    frames_used = 0

    for frame, batch in gaze_batches.items():
        n = int(batch.x_norm.size)
        if n == 0:
            continue
        if frame >= len(frames_list):
            continue

        hist = np.zeros((_IMG_H, _IMG_W), dtype=np.float64)
        _deposit_bilinear_batch(hist, batch.x_norm * (_IMG_W - 1), batch.y_norm * (_IMG_H - 1))
        density = gaussian_filter(hist, sigma=sigma_px, mode="constant")
        density_sum = float(density.sum())
        if density_sum > 0.0:
            density /= density_sum

        total_points += n
        rot_z = float(frames_list[frame]["rotation_z_radians"])

        verts_w = _apply_transform_no_recenter(
            base_verts, camera_data, rot_z,
            base_rotate_z_deg, extra_rotate_x_deg, extra_rotate_y_deg,
            transform_order,
        )
        normals_w = _apply_normal_transform(
            base_normals, rot_z,
            base_rotate_z_deg, extra_rotate_x_deg, extra_rotate_y_deg,
            transform_order,
        )

        screen_xy, w_clip = world_to_screen(verts_w, view_matrix, proj_mat)

        behind = w_clip <= 0
        to_camera = camera_world_pos[None, :] - verts_w
        front_facing = np.einsum("ij,ij->i", normals_w, to_camera) > 0.0
        culled_back_verts += int((~front_facing).sum())

        screen_xy[behind | (~front_facing)] = -1.0

        sample = bilinear_sample(density, screen_xy)
        vert_sal += n * sample
        total_weight += n
        frames_used += 1

    if total_weight > 0.0:
        vert_sal /= total_weight

    stats = {
        "total_gaze_points":  total_points,
        "frames_used":        frames_used,
        "density_img_shape":  [_IMG_H, _IMG_W],
        "sigma_px":           sigma_px,
        "nonzero_vertices":   int(np.count_nonzero(vert_sal)),
        "culled_back_verts":  culled_back_verts,
        "projection":         proj_info,
    }
    return vert_sal, stats


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

    track = _load_gaze_track(args, paths["json"])
    gaze_batches = track.gaze_batches
    gaze_stats   = _gaze_stats(track)

    smooth_gaze_data = None
    smooth_gaze_path_used = None
    smooth_gaze_dir = args.smooth_gaze_dir
    if smooth_gaze_dir and Path(str(smooth_gaze_dir)).is_dir():
        smooth_gaze_data = load_smooth_gaze(Path(str(smooth_gaze_dir)), args.model)
        if smooth_gaze_data is not None:
            smooth_gaze_path_used = str(smooth_gaze_dir)

    old_gt_ok = False
    gt: np.ndarray | None = None
    gt_mask: np.ndarray | None = None
    gt_was_smoothed = False
    old_gt_load_error: str | None = None

    if paths["gt"] is not None:
        try:
            gt, gt_mask, gt_was_smoothed = load_gt_aligned_to_obj(
                paths["gt"],
                np.asarray(mesh.vertices),
                args.gt_column,
                smooth_gaze=smooth_gaze_data,
                smooth_ratio=args.smooth_ratio,
            )
            old_gt_ok = True
        except ValueError as exc:
            if not (args.fixed_gt_dir and args.fixed_gt_dir.is_dir()):
                raise
            old_gt_load_error = str(exc)

    gt_col_name = "fixation_density" if args.gt_column == 6 else "binary_fixation"
    if gt_was_smoothed:
        gt_col_name += "_smoothed"

    n_verts = len(mesh.vertices)
    if old_gt_ok:
        n_gt_covered = int(gt_mask.sum())
        gt_coverage  = n_gt_covered / n_verts if n_verts > 0 else 0.0
        match_type   = "direct" if n_gt_covered == n_verts else "subset"
    else:
        n_gt_covered = 0
        gt_coverage  = 0.0
        match_type   = "none"

    tag_parts = []
    tag_parts.append(f"sigmapx{args.sigma_px}".replace(".", "p"))
    if args.recenter_to_bbox_center:
        tag_parts.append("recenter")
    if abs(args.extra_rotate_x_deg) > 1e-12:
        tag_parts.append(f"rotx{args.extra_rotate_x_deg}".replace(".", "p"))
    if args.projection_fov_mode != "vertical":
        tag_parts.append(args.projection_fov_mode.replace("_", ""))
    if args.transform_order != "eval":
        tag_parts.append(args.transform_order)
    if args.override_fov_deg is not None:
        tag_parts.append(f"fov{args.override_fov_deg}".replace(".", "p"))
    if gt_was_smoothed:
        tag_parts.append("gt_smoothed")
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
        transform_order=args.transform_order,
    )

    out_dir = args.output_dir / args.model / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savetxt(out_dir / f"{args.model}_screen_space_vertices.txt", vert_sal, fmt="%.10f")

    if old_gt_ok:
        results_full   = {"screen_space_gaussian": compute_metrics(vert_sal, gt)}
        results_masked = {"screen_space_gaussian": compute_metrics(vert_sal[gt_mask], gt[gt_mask])}
    else:
        results_full   = None
        results_masked = None

    report = {
        "model":      args.model,
        "tag":        tag,
        "dataset":    "SAL3D",
        "gt_file":    str(paths["gt"].name) if paths["gt"] is not None else None,
        "gt_load_error":         old_gt_load_error,
        "gt_column":  args.gt_column,
        "gt_type":    gt_col_name,
        "gt_smoothed":           gt_was_smoothed,
        "gt_smooth_gaze_dir":    smooth_gaze_path_used,
        "gt_smooth_ratio":       args.smooth_ratio if gt_was_smoothed else None,
        "gt_smooth_fixated_verts": len(smooth_gaze_data) if smooth_gaze_data else None,
        "n_vertices":      n_verts,
        "n_gt_covered":    n_gt_covered,
        "gt_coverage_pct": round(gt_coverage * 100.0, 2),
        "gt_match_type":   match_type,
        "gaze_stats":        gaze_stats,
        "participant_input": track.provenance,
        "run_stats":         run_stats,
        "method_params": {
            "sigma_px":                args.sigma_px,
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg":       args.base_rotate_z_deg,
            "extra_rotate_x_deg":      args.extra_rotate_x_deg,
            "extra_rotate_y_deg":      args.extra_rotate_y_deg,
            "override_fov_deg":        args.override_fov_deg,
            "projection_fov_mode":     args.projection_fov_mode,
            **run_stats["projection"],
            "transform_order":         args.transform_order,
            "density_image":           f"{_IMG_W}x{_IMG_H}",
        },
        "metrics_vs_gt_full_mesh":    results_full,
        "metrics_vs_gt_covered_only": results_masked,
    }

    if args.fixed_gt_dir and args.fixed_gt_dir.is_dir():
        n_faces = len(mesh.faces)
        face_sal = vert_sal[mesh.faces].mean(axis=1)
        fixed_gt, fixed_gt_path = load_fixed_face_gt(args.fixed_gt_dir, args.model, n_faces)
        manifest_path = str(args.sal3d_manifest) if args.sal3d_manifest else None
        report["metrics_vs_fixed_face_gt"] = {
            "sal3d_gt_source": "fixed_face_gt",
            "gt_domain": "face",
            "gt_path": str(fixed_gt_path),
            "manifest_path": manifest_path,
            "n_faces": n_faces,
            "screen_space_gaussian": compute_metrics(face_sal, fixed_gt),
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

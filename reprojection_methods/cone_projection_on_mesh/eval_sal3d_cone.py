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
from utils.sal3d_fixed_gt import load_fixed_face_gt  # noqa: E402

FrameGazeBatch = GazeBatch


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
            str(REPO_ROOT / "results" / "sal3d" / "cone_raycast"),
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
            "Directory with <model>_neighbors.txt files (SAL3D_final/Smooth\\ Gaze/). "
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
    """Load <model>_neighbors.txt from SAL3D_final/Smooth Gaze/.

    Returns dict mapping fixated-vertex-index → list[neighbour-vertex-indices],
    or None if the file does not exist for this model.

    File format (one record per fixated vertex):
      Line 0:   "<vertex_id> neighbors"
      Line 1–N: "<nb1>;<nb2>;...;<nb_k>;<next_vertex_id> neighbors"
      Line N+1: "<nb1>;<nb2>;...;<nb_k>"   (last vertex, no trailing marker)
    All indices are row-indices in the 20K Gaze file, not OBJ indices.
    """
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
    """Propagate raw fixation density to neighbouring vertices.

    Replicates the algorithm from the original SAL3D paper (dataset_snippet.py):
    For each fixated vertex i, spread its value to up to `ratio` nearest
    neighbours with a linearly decaying gradient from 0.9*v to 0.

    Args:
        raw_gt:      (N_gaze,) raw fixation density array (col 6 from Gaze file).
        smooth_gaze: dict from load_smooth_gaze().
        ratio:       Max neighbours per fixated vertex (paper default 500).

    Returns:
        smoothed: (N_gaze,) smoothed saliency array.
    """
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


# ── GT loading with vertex re-ordering ───────────────────────────────────────

def load_gt_aligned_to_obj(
    gaze_txt: Path,
    mesh_vertices: np.ndarray,
    gt_column: int,
    smooth_gaze: dict[int, list[int]] | None = None,
    smooth_ratio: int = 500,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Load GT saliency from Gaze/*.txt, optionally smooth, then align to OBJ.

    Pipeline:
      1. Load raw Gaze file → (N_gaze, 8) array.
      2. Extract col gt_column as raw saliency.
      3. If smooth_gaze provided: apply neighbourhood propagation in Gaze space.
      4. Align to OBJ vertex order via KD-tree (dist=0 for valid data).

    Returns:
        gt:        (N_vertices,) float array aligned to OBJ vertex indices.
                   Vertices not covered by the Gaze file receive GT = 0.
        gt_mask:   (N_vertices,) bool — True for vertices that have GT coverage.
                   For 20K direct-match OBJs this is all-True.
                   For high-res OBJs with 20K Gaze subset, only ~20K/N are True.
        smoothed:  True if GT smoothing was applied, False if raw col6 was used.
    """
    data = np.loadtxt(gaze_txt)       # (N_gaze, 8)
    gaze_xyz = data[:, :3]            # XYZ positions
    raw_sal = data[:, gt_column].astype(np.float64)

    n_verts = len(mesh_vertices)
    n_gaze  = len(gaze_xyz)

    if n_gaze > n_verts:
        raise ValueError(
            f"GT row count ({n_gaze}) > OBJ vertex count ({n_verts}). "
            "Cannot align GT to mesh."
        )

    # Optionally apply smoothing in Gaze-file row space (0..N_gaze-1)
    if smooth_gaze is not None and gt_column != 7:
        gaze_sal = apply_gt_smoothing(raw_sal, smooth_gaze, ratio=smooth_ratio)
        smoothed = True
    else:
        gaze_sal = raw_sal
        smoothed = False

    # Align Gaze rows to OBJ vertices by nearest-neighbour (dist=0)
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


# ── gaze loading (same format as 3DVA / MeshMamba) ───────────────────────────

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
        fixation_data_tag=data_tag,
    )


def _gaze_stats(track) -> dict:
    return {
        "num_rows":               track.provenance.get("csv_num_rows"),
        "num_participants":       track.provenance.get("csv_num_participants"),
        "num_points":             sum(len(b.x_norm) for b in track.gaze_batches.values()),
        "num_frames_with_points": sum(1 for b in track.gaze_batches.values() if len(b.x_norm) > 0),
    }


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

    track = _load_gaze_track(args, paths["json"])
    gaze_batches = track.gaze_batches
    gaze_stats   = _gaze_stats(track)

    # Load Smooth Gaze neighbour lists if directory is provided
    smooth_gaze_data = None
    smooth_gaze_path_used = None
    smooth_gaze_dir = args.smooth_gaze_dir
    if smooth_gaze_dir and Path(str(smooth_gaze_dir)).is_dir():
        smooth_gaze_data = load_smooth_gaze(Path(str(smooth_gaze_dir)), args.model)
        if smooth_gaze_data is not None:
            smooth_gaze_path_used = str(smooth_gaze_dir)

    # GT: load, optionally smooth, then align to OBJ vertex order
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
    if gt_was_smoothed:
        tag_parts.append("gt_smoothed")
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

    if old_gt_ok:
        results_full = {
            "raycast_nearest_vertex": compute_metrics(raycast, gt),
            "cone_gaussian_on_mesh":  compute_metrics(cone,    gt),
        }
        results_masked = {
            "raycast_nearest_vertex": compute_metrics(raycast[gt_mask], gt[gt_mask]),
            "cone_gaussian_on_mesh":  compute_metrics(cone[gt_mask],    gt[gt_mask]),
        }
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
        "gt_smoothed":          gt_was_smoothed,
        "gt_smooth_gaze_dir":   smooth_gaze_path_used,
        "gt_smooth_ratio":      args.smooth_ratio if gt_was_smoothed else None,
        "gt_smooth_fixated_verts": len(smooth_gaze_data) if smooth_gaze_data else None,
        "n_vertices":      n_verts,
        "n_gt_covered":    n_gt_covered,
        "gt_coverage_pct": round(gt_coverage * 100.0, 2),
        "gt_match_type":   match_type,
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
        "metrics_vs_gt_full_mesh":    results_full,
        "metrics_vs_gt_covered_only": results_masked,
    }

    if args.fixed_gt_dir and args.fixed_gt_dir.is_dir():
        n_faces = len(mesh.faces)
        face_raycast = raycast[mesh.faces].mean(axis=1)
        face_cone    = cone[mesh.faces].mean(axis=1)
        fixed_gt, fixed_gt_path = load_fixed_face_gt(args.fixed_gt_dir, args.model, n_faces)
        manifest_path = str(args.sal3d_manifest) if args.sal3d_manifest else None
        report["metrics_vs_fixed_face_gt"] = {
            "sal3d_gt_source": "fixed_face_gt",
            "gt_domain": "face",
            "gt_path": str(fixed_gt_path),
            "manifest_path": manifest_path,
            "n_faces": n_faces,
            "raycast_nearest_vertex": compute_metrics(face_raycast, fixed_gt),
            "cone_gaussian_on_mesh":  compute_metrics(face_cone,    fixed_gt),
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
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {report_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from metrics.mesh_space import auc_from_positive_indices, map_metrics, nss_from_positive_indices
from utils.path_defaults import resolve_dataset_root


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
DISPLAY_DIAG_IN = 24.5
VIEW_DISTANCE_CM = 85.0
DEFAULT_SIGMA_DEG = 1.0


@dataclass
class RawFixation:
    participant: str
    view_key: tuple[int, int]
    x: float
    y: float
    duration: float
    hit: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate Visual-Attention-style cone projection on Saliency3D_clear."
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=None,
        help="Root directory of Saliency3D_clear.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["hand", "bunny", "dragon"],
    )
    parser.add_argument(
        "--test-participants",
        nargs="+",
        default=["zl", "zy"],
    )
    parser.add_argument(
        "--sigma-deg",
        type=float,
        default=DEFAULT_SIGMA_DEG,
        help="Angular sigma for the cone projection. Visual Attention uses 1 degree.",
    )
    parser.add_argument(
        "--radius-sigma-mult",
        type=float,
        default=3.0,
        help="Vertex query radius in sigma units.",
    )
    parser.add_argument(
        "--min-view-samples",
        type=int,
        default=8,
        help="Minimum number of correspondences to fit a per-view projector.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(
            REPO_ROOT
            / "results"
            / "saliency3d_clear"
            / "cone_projection_on_mesh"
            / "eval_visual_attention_style_saliency3d_clear_results.json"
        ),
    )
    return parser.parse_args()


def sigma_px_from_angle(angle_deg: float) -> float:
    diag_cm = DISPLAY_DIAG_IN * 2.54
    width_cm = diag_cm * 16.0 / math.sqrt(16.0**2 + 9.0**2)
    px_per_cm = SCREEN_WIDTH / width_cm
    return VIEW_DISTANCE_CM * math.tan(math.radians(angle_deg)) * px_per_cm


def load_coordinate_map(path: Path) -> dict[tuple[int, int], tuple[float, float]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[tuple[int, int], tuple[float, float]] = {}
    for key, value in raw.items():
        a, b = key.split(",")
        out[(int(a), int(b))] = (float(value[0]), float(value[1]))
    return out


def spherical_dir(azimuth: float, elevation: float) -> np.ndarray:
    return np.array(
        [
            math.cos(elevation) * math.cos(azimuth),
            math.sin(elevation),
            math.cos(elevation) * math.sin(azimuth),
        ],
        dtype=np.float64,
    )


def load_obj_vertices(obj_path: Path) -> np.ndarray:
    verts = []
    with obj_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()[:4]
                verts.append((float(x), float(y), float(z)))
    return np.asarray(verts, dtype=np.float64)


def load_raw_fixations(model_dir: Path) -> list[RawFixation]:
    rows: list[RawFixation] = []
    for participant_file in sorted(model_dir.iterdir()):
        if not participant_file.is_file():
            continue
        participant = participant_file.name
        with participant_file.open("r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for cols in reader:
                if len(cols) < 14:
                    continue
                try:
                    x = float(cols[4])
                    y = float(cols[5])
                    vi = int(cols[8])
                    vj = int(cols[9])
                    duration = float(cols[10])
                    hit = np.array([float(cols[11]), float(cols[12]), float(cols[13])], dtype=np.float64)
                except ValueError:
                    continue
                if np.isnan(x) or np.isnan(y) or np.isnan(duration) or np.isnan(hit).any():
                    continue
                rows.append(
                    RawFixation(
                        participant=participant,
                        view_key=(vi, vj),
                        x=x,
                        y=y,
                        duration=max(duration, 0.0),
                        hit=hit,
                    )
                )
    return rows


def fit_projector(hits: np.ndarray, screen_xy: np.ndarray) -> tuple[np.ndarray, float]:
    X = np.concatenate([hits, np.ones((len(hits), 1), dtype=np.float64)], axis=1)
    coef, *_ = np.linalg.lstsq(X, screen_xy, rcond=None)
    pred = X @ coef
    rmse = float(np.sqrt(np.mean(np.sum((pred - screen_xy) ** 2, axis=1))))
    return coef, rmse


def project_points(points: np.ndarray, projector: np.ndarray) -> np.ndarray:
    X = np.concatenate([points, np.ones((len(points), 1), dtype=np.float64)], axis=1)
    return X @ projector


def build_view_models(
    vertices: np.ndarray,
    rows: list[RawFixation],
    coord_map: dict[tuple[int, int], tuple[float, float]],
    sigma_px: float,
    min_view_samples: int,
) -> tuple[dict[tuple[int, int], dict[str, object]], dict[str, float]]:
    center = vertices.mean(axis=0)
    by_view: dict[tuple[int, int], list[RawFixation]] = defaultdict(list)
    for row in rows:
        by_view[row.view_key].append(row)

    models: dict[tuple[int, int], dict[str, object]] = {}
    rmses = []
    skipped_small = 0
    skipped_missing = 0

    for view_key, view_rows in by_view.items():
        if view_key not in coord_map:
            skipped_missing += len(view_rows)
            continue
        if len(view_rows) < min_view_samples:
            skipped_small += len(view_rows)
            continue

        hits = np.stack([row.hit for row in view_rows], axis=0)
        xy = np.array([[row.x, row.y] for row in view_rows], dtype=np.float64)
        projector, rmse = fit_projector(hits, xy)
        rmses.append(rmse)

        az, el = coord_map[view_key]
        view_dir = spherical_dir(az, el)
        hit_sign = np.sign(np.mean((hits - center) @ view_dir))
        if hit_sign == 0:
            hit_sign = 1.0
        visible_mask = ((vertices - center) @ view_dir) * hit_sign >= 0.0
        visible_idx = np.flatnonzero(visible_mask)
        visible_xy = project_points(vertices[visible_mask], projector)
        tree = cKDTree(visible_xy)

        models[view_key] = {
            "projector": projector,
            "rmse_px": rmse,
            "visible_idx": visible_idx,
            "visible_xy": visible_xy,
            "tree": tree,
        }

    summary = {
        "num_views_total": float(len(by_view)),
        "num_views_fitted": float(len(models)),
        "projection_rmse_px_median": float(np.median(rmses)) if rmses else float("nan"),
        "projection_rmse_px_mean": float(np.mean(rmses)) if rmses else float("nan"),
        "rows_skipped_missing_coordinate": float(skipped_missing),
        "rows_skipped_too_few_view_samples": float(skipped_small),
        "sigma_px": float(sigma_px),
    }
    return models, summary


def accumulate_cone_map(
    vertices: np.ndarray,
    rows: list[RawFixation],
    view_models: dict[tuple[int, int], dict[str, object]],
    sigma_px: float,
    radius_sigma_mult: float,
) -> tuple[np.ndarray, dict[str, float]]:
    out = np.zeros(len(vertices), dtype=np.float64)
    radius = radius_sigma_mult * sigma_px
    used = 0
    skipped = 0
    touched_vertices = 0

    for row in rows:
        vm = view_models.get(row.view_key)
        if vm is None:
            skipped += 1
            continue
        tree: cKDTree = vm["tree"]  # type: ignore[assignment]
        visible_idx: np.ndarray = vm["visible_idx"]  # type: ignore[assignment]
        visible_xy: np.ndarray = vm["visible_xy"]  # type: ignore[assignment]

        idxs = tree.query_ball_point([row.x, row.y], r=radius)
        if not idxs:
            idxs = [int(tree.query([row.x, row.y], k=1)[1])]
        local_xy = visible_xy[idxs]
        d2 = np.sum((local_xy - np.array([row.x, row.y], dtype=np.float64)) ** 2, axis=1)
        weights = np.exp(-0.5 * d2 / (sigma_px**2))
        weights *= row.duration
        global_idx = visible_idx[np.asarray(idxs, dtype=np.int64)]
        out[global_idx] += weights
        touched_vertices += len(global_idx)
        used += 1

    total = float(out.sum())
    if total > 0.0:
        out /= total

    stats = {
        "rows_used": float(used),
        "rows_skipped": float(skipped),
        "avg_vertices_touched_per_row": float(touched_vertices / used) if used else 0.0,
    }
    return out, stats


def build_raw_vertex_targets(
    vertices: np.ndarray,
    rows: list[RawFixation],
) -> tuple[np.ndarray, np.ndarray]:
    tree = cKDTree(vertices)
    hit_points = np.stack([row.hit for row in rows], axis=0)
    durations = np.array([row.duration for row in rows], dtype=np.float64)
    _, idx = tree.query(hit_points, k=1)
    sparse = np.zeros(len(vertices), dtype=np.float64)
    np.add.at(sparse, idx, durations)
    total = sparse.sum()
    if total > 0.0:
        sparse /= total
    return sparse, np.asarray(idx, dtype=np.int64)


def compute_fixation_metrics(pred: np.ndarray, positive_indices: np.ndarray) -> dict[str, float]:
    return {
        "NSS_raw_vertices": nss_from_positive_indices(pred, positive_indices),
        "AUC_raw_vertices": auc_from_positive_indices(pred, positive_indices),
        "num_positive_vertices_unique": float(np.unique(positive_indices).size),
        "num_positive_vertices_total": float(len(positive_indices)),
    }


def main() -> None:
    args = parse_args()
    dataset_root = resolve_dataset_root(
        args.dataset_root,
        env_var="SALIENCY3D_CLEAR_ROOT",
        dataset_name="Saliency3D_clear",
        example_path="/Users/admin/Documents/LAB/SALIENCY_code/Dataset (Clear)/Saliency3D_clear",
    )
    sigma_px = sigma_px_from_angle(args.sigma_deg)
    coord_map = load_coordinate_map(
        dataset_root / "doi-10.18419-darus-4101" / "3DSaliency" / "coordinate.json"
    )
    results = []

    exp1_root = dataset_root / "3D_gaze_data" / "Code" / "Exp1"
    obj_root = dataset_root / "obj"

    for model in args.models:
        vertices = load_obj_vertices(obj_root / f"{model}.obj")
        rows = load_raw_fixations(exp1_root / model)
        train_rows = [row for row in rows if row.participant not in args.test_participants]
        test_rows = [row for row in rows if row.participant in args.test_participants]
        if not train_rows or not test_rows:
            raise SystemExit(f"Train/test split is empty for model {model}.")

        view_models, projection_summary = build_view_models(
            vertices=vertices,
            rows=rows,
            coord_map=coord_map,
            sigma_px=sigma_px,
            min_view_samples=args.min_view_samples,
        )
        train_map, train_stats = accumulate_cone_map(
            vertices=vertices,
            rows=train_rows,
            view_models=view_models,
            sigma_px=sigma_px,
            radius_sigma_mult=args.radius_sigma_mult,
        )
        test_map, test_stats = accumulate_cone_map(
            vertices=vertices,
            rows=test_rows,
            view_models=view_models,
            sigma_px=sigma_px,
            radius_sigma_mult=args.radius_sigma_mult,
        )
        raw_test_sparse, raw_test_indices = build_raw_vertex_targets(vertices, test_rows)

        result = {
            "model": model,
            "num_vertices": int(len(vertices)),
            "num_rows_total": int(len(rows)),
            "num_rows_train": int(len(train_rows)),
            "num_rows_test": int(len(test_rows)),
            "train_participants": sorted({row.participant for row in train_rows}),
            "test_participants": sorted({row.participant for row in test_rows}),
            "sigma_deg": float(args.sigma_deg),
            "sigma_px": float(sigma_px),
            "projection_summary": projection_summary,
            "train_accumulation": train_stats,
            "test_accumulation": test_stats,
            "train_vs_test_cone_map": map_metrics(train_map, test_map),
            "train_vs_test_raw_vertices": compute_fixation_metrics(train_map, raw_test_indices),
            "raw_test_sparse_vs_test_cone_map": map_metrics(raw_test_sparse, test_map),
        }
        results.append(result)

    payload = {
        "notes": {
            "dataset_root": str(dataset_root),
            "method": "Visual-Attention-style proxy: per-view 3D->2D affine projection fitted from raw hits, then Gaussian cone on mesh vertices in projected screen space.",
            "sigma_deg": args.sigma_deg,
            "sigma_px": sigma_px,
            "limitation": "This is not the original author code of either paper. It is a pragmatic transfer of the cone-projection idea to Saliency3D_clear using the available raw 2D gaze, view indices, and 3D hit points.",
            "gt_definition": "Held-out test participants projected with the same cone-style pipeline; additional AUC/NSS use raw held-out hit vertices as positives.",
        },
        "results": results,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"\nSaved report: {args.output_json}")


if __name__ == "__main__":
    main()

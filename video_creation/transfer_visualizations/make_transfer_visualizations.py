#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/mplconfig_codex")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.path_defaults import resolve_dataset_root


SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
DISPLAY_DIAG_IN = 24.5
VIEW_DISTANCE_CM = 85.0


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
        description="Create transfer visualizations for Saliency3D_clear methods."
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
    parser.add_argument("--screen-sigma-px", type=float, default=26.3)
    parser.add_argument("--cone-sigma-deg", type=float, default=1.0)
    parser.add_argument("--radius-sigma-mult", type=float, default=3.0)
    parser.add_argument("--min-view-samples", type=int, default=8)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(REPO_ROOT / "results" / "saliency3d_clear" / "transfer_visualizations"),
    )
    parser.add_argument(
        "--layout",
        choices=["combined", "methods_only"],
        default="combined",
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


def choose_top_view_from_rows(rows: list[RawFixation]) -> tuple[int, int]:
    weights: dict[tuple[int, int], float] = defaultdict(float)
    for row in rows:
        weights[row.view_key] += row.duration
    return max(weights.items(), key=lambda kv: kv[1])[0]


def deposit_bilinear(canvas: np.ndarray, x: float, y: float, weight: float) -> None:
    x = float(np.clip(x, 0.0, SCREEN_WIDTH - 1.0))
    y = float(np.clip(y, 0.0, SCREEN_HEIGHT - 1.0))
    x0 = int(np.floor(x))
    y0 = int(np.floor(y))
    x1 = min(x0 + 1, SCREEN_WIDTH - 1)
    y1 = min(y0 + 1, SCREEN_HEIGHT - 1)
    dx = x - x0
    dy = y - y0
    canvas[y0, x0] += weight * (1.0 - dx) * (1.0 - dy)
    canvas[y0, x1] += weight * dx * (1.0 - dy)
    canvas[y1, x0] += weight * (1.0 - dx) * dy
    canvas[y1, x1] += weight * dx * dy


def build_density_map(rows: list[RawFixation], sigma_px: float) -> np.ndarray:
    hist = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH), dtype=np.float32)
    for row in rows:
        deposit_bilinear(hist, row.x, row.y, row.duration)
    density = gaussian_filter(hist, sigma=sigma_px, mode="constant")
    total = float(density.sum())
    if total > 0.0:
        density /= total
    return density


def compute_screen_metrics(pred: np.ndarray, gt: np.ndarray, test_rows: list[RawFixation]) -> tuple[float, float, float]:
    p = pred.ravel().astype(np.float64)
    g = gt.ravel().astype(np.float64)
    cc = float(np.corrcoef(p, g)[0, 1])

    zmap = (pred - pred.mean()) / (pred.std() + 1e-12)
    nss = float(np.mean([zmap[int(round(r.y)), int(round(r.x))] for r in test_rows]))

    mask = np.zeros((SCREEN_HEIGHT, SCREEN_WIDTH), dtype=np.uint8)
    for r in test_rows:
        x = int(np.clip(round(r.x), 0, SCREEN_WIDTH - 1))
        y = int(np.clip(round(r.y), 0, SCREEN_HEIGHT - 1))
        mask[y, x] = 1
    pos_scores = pred[mask == 1].ravel()
    neg_scores = pred[mask == 0].ravel()
    ranks = np.argsort(np.argsort(np.concatenate([pos_scores, neg_scores]))) + 1
    m = len(pos_scores)
    n = len(neg_scores)
    r_pos = ranks[:m].sum()
    auc = float((r_pos - m * (m + 1) / 2) / (m * n))
    return auc, nss, cc


def fit_projector(hits: np.ndarray, screen_xy: np.ndarray) -> tuple[np.ndarray, float]:
    X = np.concatenate([hits, np.ones((len(hits), 1), dtype=np.float64)], axis=1)
    coef, *_ = np.linalg.lstsq(X, screen_xy, rcond=None)
    pred = X @ coef
    rmse = float(np.sqrt(np.mean(np.sum((pred - screen_xy) ** 2, axis=1))))
    return coef, rmse


def project_points(points: np.ndarray, projector: np.ndarray) -> np.ndarray:
    X = np.concatenate([points, np.ones((len(points), 1), dtype=np.float64)], axis=1)
    return X @ projector


def compute_centered_viewport(point_sets: list[np.ndarray]) -> tuple[float, float, float, float]:
    valid_sets = []
    for pts in point_sets:
        if pts.size == 0:
            continue
        pts = pts[np.isfinite(pts).all(axis=1)]
        if pts.size == 0:
            continue
        in_screen = (
            (pts[:, 0] >= 0.0)
            & (pts[:, 0] <= SCREEN_WIDTH)
            & (pts[:, 1] >= 0.0)
            & (pts[:, 1] <= SCREEN_HEIGHT)
        )
        if np.count_nonzero(in_screen) >= 16:
            pts = pts[in_screen]
        valid_sets.append(pts)

    if not valid_sets:
        return 0.0, float(SCREEN_WIDTH), 0.0, float(SCREEN_HEIGHT)

    mins = np.array([pts.min(axis=0) for pts in valid_sets], dtype=np.float64)
    maxs = np.array([pts.max(axis=0) for pts in valid_sets], dtype=np.float64)
    x_lo = float(mins[:, 0].min())
    y_lo = float(mins[:, 1].min())
    x_hi = float(maxs[:, 0].max())
    y_hi = float(maxs[:, 1].max())

    width = max(32.0, x_hi - x_lo)
    height = max(32.0, y_hi - y_lo)
    side = max(width, height) * 1.08
    cx = (x_lo + x_hi) * 0.5
    cy = (y_lo + y_hi) * 0.5
    half = side * 0.5

    x0 = cx - half
    x1 = cx + half
    y0 = cy - half
    y1 = cy + half

    if x0 < 0.0:
        x1 -= x0
        x0 = 0.0
    if x1 > SCREEN_WIDTH:
        x0 -= x1 - SCREEN_WIDTH
        x1 = float(SCREEN_WIDTH)
    if y0 < 0.0:
        y1 -= y0
        y0 = 0.0
    if y1 > SCREEN_HEIGHT:
        y0 -= y1 - SCREEN_HEIGHT
        y1 = float(SCREEN_HEIGHT)

    x0 = max(0.0, x0)
    y0 = max(0.0, y0)
    x1 = min(float(SCREEN_WIDTH), x1)
    y1 = min(float(SCREEN_HEIGHT), y1)
    return x0, x1, y0, y1


def build_single_view_model(
    vertices: np.ndarray,
    rows_for_view: list[RawFixation],
    coord_map: dict[tuple[int, int], tuple[float, float]],
    view_key: tuple[int, int],
):
    hits = np.stack([row.hit for row in rows_for_view], axis=0)
    xy = np.array([[row.x, row.y] for row in rows_for_view], dtype=np.float64)
    projector, rmse = fit_projector(hits, xy)

    center = vertices.mean(axis=0)
    az, el = coord_map[view_key]
    view_dir = spherical_dir(az, el)
    hit_sign = np.sign(np.mean((hits - center) @ view_dir))
    if hit_sign == 0:
        hit_sign = 1.0
    visible_mask = ((vertices - center) @ view_dir) * hit_sign >= 0.0
    visible_idx = np.flatnonzero(visible_mask)
    visible_xy = project_points(vertices[visible_mask], projector)
    tree = cKDTree(visible_xy)
    return {
        "projector": projector,
        "rmse_px": rmse,
        "visible_idx": visible_idx,
        "visible_xy": visible_xy,
        "tree": tree,
    }


def accumulate_single_view_cone_map(
    vertices: np.ndarray,
    rows: list[RawFixation],
    view_model: dict[str, object],
    sigma_px: float,
    radius_sigma_mult: float,
) -> np.ndarray:
    out = np.zeros(len(vertices), dtype=np.float64)
    radius = radius_sigma_mult * sigma_px
    tree: cKDTree = view_model["tree"]  # type: ignore[assignment]
    visible_idx: np.ndarray = view_model["visible_idx"]  # type: ignore[assignment]
    visible_xy: np.ndarray = view_model["visible_xy"]  # type: ignore[assignment]
    for row in rows:
        idxs = tree.query_ball_point([row.x, row.y], r=radius)
        if not idxs:
            idxs = [int(tree.query([row.x, row.y], k=1)[1])]
        local_xy = visible_xy[idxs]
        d2 = np.sum((local_xy - np.array([row.x, row.y], dtype=np.float64)) ** 2, axis=1)
        weights = np.exp(-0.5 * d2 / (sigma_px**2))
        weights *= row.duration
        global_idx = visible_idx[np.asarray(idxs, dtype=np.int64)]
        out[global_idx] += weights
    total = float(out.sum())
    if total > 0.0:
        out /= total
    return out


def compute_cone_metrics(train_map: np.ndarray, test_map: np.ndarray, test_rows: list[RawFixation], vertices: np.ndarray) -> tuple[float, float, float]:
    cc = float(np.corrcoef(train_map, test_map)[0, 1])
    z = (train_map - train_map.mean()) / (train_map.std() + 1e-12)
    tree = cKDTree(vertices)
    hit_points = np.stack([r.hit for r in test_rows], axis=0)
    _, idx = tree.query(hit_points, k=1)
    nss = float(np.mean(z[idx]))
    labels = np.zeros(len(train_map), dtype=np.uint8)
    labels[np.unique(idx)] = 1
    pos_scores = train_map[labels == 1]
    neg_scores = train_map[labels == 0]
    ranks = np.argsort(np.argsort(np.concatenate([pos_scores, neg_scores]))) + 1
    m = len(pos_scores)
    n = len(neg_scores)
    r_pos = ranks[:m].sum()
    auc = float((r_pos - m * (m + 1) / 2) / (m * n))
    return auc, nss, cc


def render_model_figure(
    model: str,
    view_key: tuple[int, int],
    screen_train: list[RawFixation],
    screen_test: list[RawFixation],
    screen_pred: np.ndarray,
    screen_gt: np.ndarray,
    screen_metrics: tuple[float, float, float],
    cone_train_map: np.ndarray,
    cone_test_map: np.ndarray,
    cone_metrics: tuple[float, float, float],
    view_model: dict[str, object],
    out_path: Path,
) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(16, 10), constrained_layout=True)

    visible_xy: np.ndarray = view_model["visible_xy"]  # type: ignore[assignment]
    visible_idx: np.ndarray = view_model["visible_idx"]  # type: ignore[assignment]
    projector: np.ndarray = view_model["projector"]  # type: ignore[assignment]
    train_hits_xy = project_points(np.stack([r.hit for r in screen_train], axis=0), projector)
    test_hits_xy = project_points(np.stack([r.hit for r in screen_test], axis=0), projector)

    screen_train_xy = np.array([[r.x, r.y] for r in screen_train], dtype=np.float64)
    screen_test_xy = np.array([[r.x, r.y] for r in screen_test], dtype=np.float64)
    top_x0, top_x1, top_y0, top_y1 = compute_centered_viewport(
        [screen_train_xy, screen_test_xy, train_hits_xy, test_hits_xy]
    )
    bottom_x0, bottom_x1, bottom_y0, bottom_y1 = compute_centered_viewport(
        [visible_xy]
    )

    sc = axes[0, 0].scatter(
        [r.x for r in screen_train],
        [r.y for r in screen_train],
        s=np.clip([r.duration for r in screen_train], 8, 80),
        c=[r.duration for r in screen_train],
        cmap="magma",
        alpha=0.65,
        edgecolors="none",
    )
    axes[0, 0].set_xlim(top_x0, top_x1)
    axes[0, 0].set_ylim(top_y1, top_y0)
    axes[0, 0].set_title("Screen Raw Train Points")
    fig.colorbar(sc, ax=axes[0, 0], fraction=0.046, pad=0.02)

    im1 = axes[0, 1].imshow(
        screen_pred,
        cmap="inferno",
        origin="upper",
        extent=[0, SCREEN_WIDTH, SCREEN_HEIGHT, 0],
    )
    axes[0, 1].set_xlim(top_x0, top_x1)
    axes[0, 1].set_ylim(top_y1, top_y0)
    axes[0, 1].set_title(
        f"Screen Prediction\nAUC={screen_metrics[0]:.3f} NSS={screen_metrics[1]:.3f} CC={screen_metrics[2]:.3f}"
    )
    fig.colorbar(im1, ax=axes[0, 1], fraction=0.046, pad=0.02)

    im2 = axes[0, 2].imshow(
        screen_gt,
        cmap="inferno",
        origin="upper",
        extent=[0, SCREEN_WIDTH, SCREEN_HEIGHT, 0],
    )
    axes[0, 2].scatter(
        [r.x for r in screen_test],
        [r.y for r in screen_test],
        s=6,
        c="cyan",
        alpha=0.35,
        edgecolors="none",
    )
    axes[0, 2].set_xlim(top_x0, top_x1)
    axes[0, 2].set_ylim(top_y1, top_y0)
    axes[0, 2].set_title("Screen GT (Held-out Test)")
    fig.colorbar(im2, ax=axes[0, 2], fraction=0.046, pad=0.02)
    axes[1, 0].scatter(
        visible_xy[:, 0],
        visible_xy[:, 1],
        s=0.2,
        c="lightgray",
        alpha=0.20,
        edgecolors="none",
    )
    axes[1, 0].scatter(
        train_hits_xy[:, 0],
        train_hits_xy[:, 1],
        s=np.clip([r.duration for r in screen_train], 8, 80),
        c=[r.duration for r in screen_train],
        cmap="viridis",
        alpha=0.65,
        edgecolors="none",
    )
    axes[1, 0].set_xlim(bottom_x0, bottom_x1)
    axes[1, 0].set_ylim(bottom_y1, bottom_y0)
    axes[1, 0].set_title("Cone Transfer: Projected 3D Hits")

    vmax = float(max(cone_train_map.max(), cone_test_map.max()))
    sc1 = axes[1, 1].scatter(
        visible_xy[:, 0],
        visible_xy[:, 1],
        c=cone_train_map[visible_idx],
        s=0.35,
        cmap="inferno",
        vmin=0.0,
        vmax=vmax if vmax > 0 else 1.0,
        edgecolors="none",
    )
    axes[1, 1].set_xlim(bottom_x0, bottom_x1)
    axes[1, 1].set_ylim(bottom_y1, bottom_y0)
    axes[1, 1].set_title(
        f"Cone Prediction on Mesh\nAUC={cone_metrics[0]:.3f} NSS={cone_metrics[1]:.3f} CC={cone_metrics[2]:.3f}"
    )
    fig.colorbar(sc1, ax=axes[1, 1], fraction=0.046, pad=0.02)

    sc2 = axes[1, 2].scatter(
        visible_xy[:, 0],
        visible_xy[:, 1],
        c=cone_test_map[visible_idx],
        s=0.35,
        cmap="inferno",
        vmin=0.0,
        vmax=vmax if vmax > 0 else 1.0,
        edgecolors="none",
    )
    axes[1, 2].set_xlim(bottom_x0, bottom_x1)
    axes[1, 2].set_ylim(bottom_y1, bottom_y0)
    axes[1, 2].set_title("Cone GT on Mesh (Held-out Test)")
    fig.colorbar(sc2, ax=axes[1, 2], fraction=0.046, pad=0.02)

    for ax in axes.ravel():
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")

    fig.suptitle(
        f"{model} | view={view_key} | screen sigma=26.3 px | cone sigma≈1° ({sigma_px_from_angle(1.0):.2f} px)",
        fontsize=14,
    )
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def render_methods_only_figure(
    model: str,
    view_key: tuple[int, int],
    screen_pred: np.ndarray,
    screen_gt: np.ndarray,
    screen_metrics: tuple[float, float, float],
    cone_train_map: np.ndarray,
    cone_test_map: np.ndarray,
    cone_metrics: tuple[float, float, float],
    view_model: dict[str, object],
    out_path: Path,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 12), constrained_layout=True)

    visible_xy: np.ndarray = view_model["visible_xy"]  # type: ignore[assignment]
    visible_idx: np.ndarray = view_model["visible_idx"]  # type: ignore[assignment]
    x0, x1, y0, y1 = compute_centered_viewport([visible_xy])

    for ax in axes.ravel():
        ax.scatter(
            visible_xy[:, 0],
            visible_xy[:, 1],
            s=0.18,
            c="lightgray",
            alpha=0.22,
            edgecolors="none",
            zorder=1,
        )
        ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")

    im0 = axes[0, 0].imshow(
        screen_pred,
        cmap="inferno",
        origin="upper",
        extent=[0, SCREEN_WIDTH, SCREEN_HEIGHT, 0],
        alpha=0.90,
        zorder=2,
    )
    axes[0, 0].scatter(
        visible_xy[:, 0],
        visible_xy[:, 1],
        s=0.14,
        c="white",
        alpha=0.05,
        edgecolors="none",
        zorder=3,
    )
    axes[0, 0].set_title(
        f"Screen Prediction\nAUC={screen_metrics[0]:.3f} NSS={screen_metrics[1]:.3f} CC={screen_metrics[2]:.3f}"
    )
    fig.colorbar(im0, ax=axes[0, 0], fraction=0.046, pad=0.02)

    im1 = axes[0, 1].imshow(
        screen_gt,
        cmap="inferno",
        origin="upper",
        extent=[0, SCREEN_WIDTH, SCREEN_HEIGHT, 0],
        alpha=0.90,
        zorder=2,
    )
    axes[0, 1].scatter(
        visible_xy[:, 0],
        visible_xy[:, 1],
        s=0.14,
        c="white",
        alpha=0.05,
        edgecolors="none",
        zorder=3,
    )
    axes[0, 1].set_title("Screen GT from Saliency3D_clear Test Fixations")
    fig.colorbar(im1, ax=axes[0, 1], fraction=0.046, pad=0.02)

    vmax = float(max(cone_train_map.max(), cone_test_map.max()))
    sc0 = axes[1, 0].scatter(
        visible_xy[:, 0],
        visible_xy[:, 1],
        c=cone_train_map[visible_idx],
        s=0.35,
        cmap="inferno",
        vmin=0.0,
        vmax=vmax if vmax > 0 else 1.0,
        edgecolors="none",
        zorder=2,
    )
    axes[1, 0].set_title(
        f"Cone Prediction on Mesh\nAUC={cone_metrics[0]:.3f} NSS={cone_metrics[1]:.3f} CC={cone_metrics[2]:.3f}"
    )
    fig.colorbar(sc0, ax=axes[1, 0], fraction=0.046, pad=0.02)

    sc1 = axes[1, 1].scatter(
        visible_xy[:, 0],
        visible_xy[:, 1],
        c=cone_test_map[visible_idx],
        s=0.35,
        cmap="inferno",
        vmin=0.0,
        vmax=vmax if vmax > 0 else 1.0,
        edgecolors="none",
        zorder=2,
    )
    axes[1, 1].set_title("Cone GT from Saliency3D_clear Test Fixations")
    fig.colorbar(sc1, ax=axes[1, 1], fraction=0.046, pad=0.02)

    fig.suptitle(
        f"{model} | view={view_key} | top: screen sigma=26.3 px | bottom: cone sigma≈1° ({sigma_px_from_angle(1.0):.2f} px)",
        fontsize=14,
    )
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    dataset_root = resolve_dataset_root(
        args.dataset_root,
        env_var="SALIENCY3D_CLEAR_ROOT",
        dataset_name="Saliency3D_clear",
        example_path="/Users/admin/Documents/LAB/SALIENCY_code/Dataset (Clear)/Saliency3D_clear",
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)

    coord_map = load_coordinate_map(
        dataset_root / "doi-10.18419-darus-4101" / "3DSaliency" / "coordinate.json"
    )
    cone_sigma_px = sigma_px_from_angle(args.cone_sigma_deg)

    summary = []
    for model in args.models:
        rows = load_raw_fixations(dataset_root / "3D_gaze_data" / "Code" / "Exp1" / model)
        vertices = load_obj_vertices(dataset_root / "obj" / f"{model}.obj")
        view_key = choose_top_view_from_rows(rows)

        rows_view = [r for r in rows if r.view_key == view_key]
        train_rows = [r for r in rows_view if r.participant not in args.test_participants]
        test_rows = [r for r in rows_view if r.participant in args.test_participants]
        if len(train_rows) < args.min_view_samples or len(test_rows) < 2:
            raise SystemExit(
                f"Too few rows for model={model}, view={view_key}: train={len(train_rows)} test={len(test_rows)}"
            )

        screen_pred = build_density_map(train_rows, args.screen_sigma_px)
        screen_gt = build_density_map(test_rows, args.screen_sigma_px)
        screen_metrics = compute_screen_metrics(screen_pred, screen_gt, test_rows)

        view_model = build_single_view_model(vertices, rows_view, coord_map, view_key)
        cone_train_map = accumulate_single_view_cone_map(
            vertices, train_rows, view_model, cone_sigma_px, args.radius_sigma_mult
        )
        cone_test_map = accumulate_single_view_cone_map(
            vertices, test_rows, view_model, cone_sigma_px, args.radius_sigma_mult
        )
        cone_metrics = compute_cone_metrics(cone_train_map, cone_test_map, test_rows, vertices)

        suffix = "comparison" if args.layout == "combined" else "methods_only"
        out_path = args.output_dir / f"{model}_view_{view_key[0]}_{view_key[1]}_{suffix}.png"
        if args.layout == "combined":
            render_model_figure(
                model=model,
                view_key=view_key,
                screen_train=train_rows,
                screen_test=test_rows,
                screen_pred=screen_pred,
                screen_gt=screen_gt,
                screen_metrics=screen_metrics,
                cone_train_map=cone_train_map,
                cone_test_map=cone_test_map,
                cone_metrics=cone_metrics,
                view_model=view_model,
                out_path=out_path,
            )
        else:
            render_methods_only_figure(
                model=model,
                view_key=view_key,
                screen_pred=screen_pred,
                screen_gt=screen_gt,
                screen_metrics=screen_metrics,
                cone_train_map=cone_train_map,
                cone_test_map=cone_test_map,
                cone_metrics=cone_metrics,
                view_model=view_model,
                out_path=out_path,
            )

        summary.append(
            {
                "model": model,
                "view_key": list(view_key),
                "num_rows_view_total": len(rows_view),
                "num_rows_view_train": len(train_rows),
                "num_rows_view_test": len(test_rows),
                "screen_metrics": {
                    "AUC": screen_metrics[0],
                    "NSS": screen_metrics[1],
                    "CC": screen_metrics[2],
                },
                "cone_metrics": {
                    "AUC": cone_metrics[0],
                    "NSS": cone_metrics[1],
                    "CC": cone_metrics[2],
                },
                "projection_rmse_px": view_model["rmse_px"],
                "dataset_root": str(dataset_root),
                "image": str(out_path),
            }
        )

    summary_path = args.output_dir / "comparison_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved summary: {summary_path}")


if __name__ == "__main__":
    main()

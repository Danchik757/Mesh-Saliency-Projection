#!/usr/bin/env python3
"""
Visual sanity check for the MeshMamba cone_gaussian_on_mesh projection method.

Produces PNG images to verify that:
  1. The 2D gaze distribution and projected mesh faces are spatially aligned.
  2. Cone-spread saliency falls on plausible face regions.
  3. The accumulated predicted cone map looks plausible relative to GT.

=== Three panels per frame ===

  LEFT   — Gaze density  (INPUT / intuitive reference)
           2D histogram of raw eye-tracker fixations for that frame,
           blurred for display only.
           Cyan dots = individual raw gaze points.

  MIDDLE — Predicted cone saliency  (OUR RESULT)
           Each dot = one visible face centroid projected to screen.
           Colour = per-face cone saliency contribution for that frame.

  RIGHT  — GT saliency  (REFERENCE / GROUND TRUTH)
           Same face-centroid projection but coloured by the GT per-face CSV.

=== Summary image ===

  Two panels: accumulated predicted cone saliency vs GT at a mid-rotation frame.

=== Usage ===

  source test/env/local_paths.example.sh
  /Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 \\
      gt_visualizations/preview_meshmamba_cone_alignment.py \\
      --model Starfruit_L3 --texture-type non_texture \\
      --output-dir /tmp/preview_meshmamba_cone
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
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from reprojection_methods.cone_projection_on_mesh.eval_meshmamba_cone import (
    FrameGazeBatch,
    apply_model_transform,
    load_gaze_batches,
    resolve_model_paths,
    resolve_projection_matrix,
    screen_to_rays,
)


W_OUT = 640
H_OUT = 360
LABEL_H = 22
HEADER_H = 24
IMG_W = 1920
IMG_H = 1080
METHOD_NAME = "cone_gaussian_on_mesh"


def _env_path(primary: str, secondary: str, fallback: str = "") -> Path:
    return Path(os.environ.get(primary) or os.environ.get(secondary) or fallback)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Starfruit_L3")
    p.add_argument("--texture-type", choices=["non_texture", "rgb_texture"], default="non_texture")
    p.add_argument("--sigma-px", type=float, default=26.3, help="Display-only blur for the left gaze-density panel.")
    p.add_argument("--sigma-deg", type=float, default=1.0)
    p.add_argument("--radius-sigma-mult", type=float, default=3.0)
    p.add_argument(
        "--preview-frames",
        nargs="+",
        type=int,
        default=None,
        help="Frame indices to preview. Default: 3 evenly spaced.",
    )
    p.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional cap on processed gaze frames for quick smoke/debug runs.",
    )
    p.add_argument("--output-dir", type=Path, default=Path("/tmp/preview_meshmamba_cone"))
    p.add_argument(
        "--dataset-root",
        type=Path,
        default=None,
    )
    p.add_argument(
        "--csv-root",
        type=Path,
        default=None,
    )
    p.add_argument(
        "--json-root",
        type=Path,
        default=None,
    )
    p.add_argument(
        "--recenter-to-bbox-center",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    p.add_argument("--base-rotate-z-deg", type=float, default=0.0)
    p.add_argument("--extra-rotate-x-deg", type=float, default=90.0)
    p.add_argument("--extra-rotate-y-deg", type=float, default=0.0)
    p.add_argument("--override-fov-deg", type=float, default=None)
    p.add_argument(
        "--projection-fov-mode",
        choices=["vertical", "horizontal_to_vertical", "json"],
        default="horizontal_to_vertical",
    )
    p.add_argument(
        "--transform-order",
        choices=["eval", "blender_rig"],
        default="blender_rig",
    )
    args = p.parse_args()

    if args.dataset_root is None:
        args.dataset_root = _env_path(
            "MESHMAMBA_NON_TEXTURE_ROOT",
            "REPROJECT_DATASET_MESHMAMBA_ROOT",
        )

    csv_secondary = (
        "REPROJECT_GAZE_CSV_MESHMAMBA_RGB_TEXTURE_ROOT"
        if args.texture_type == "rgb_texture"
        else "REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT"
    )
    if args.csv_root is None:
        args.csv_root = _env_path("MESHMAMBA_CSV_ROOT", csv_secondary)

    json_secondary = (
        "REPROJECT_GAZE_JSON_MESHMAMBA_RGB_TEXTURE_ROOT"
        if args.texture_type == "rgb_texture"
        else "REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT"
    )
    if args.json_root is None:
        args.json_root = _env_path("MESHMAMBA_JSON_ROOT", json_secondary)

    return args


def _normalise(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float64)
    lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def _apply_colormap_hot(arr01: np.ndarray) -> np.ndarray:
    r = np.clip(arr01 * 3.0, 0, 1)
    g = np.clip(arr01 * 3.0 - 1.0, 0, 1)
    b = np.clip(arr01 * 3.0 - 2.0, 0, 1)
    return (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)


def _apply_colormap_plasma(val01: float) -> tuple[int, int, int]:
    r = int(np.clip(val01 * 2.5 - 0.2, 0, 1) * 255)
    g = int(np.clip(val01 * 1.5 - 0.3, 0, 1) * 255)
    b = int(np.clip(1.0 - val01 * 1.8, 0, 1) * 255)
    return (r, g, b)


def make_density_panel(density: np.ndarray, title: str) -> Image.Image:
    dn = _normalise(density)
    dn_resized = np.array(
        Image.fromarray(_apply_colormap_hot(dn)).resize((W_OUT, H_OUT), Image.BILINEAR)
    )
    img = Image.fromarray(dn_resized)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, H_OUT - LABEL_H, W_OUT, H_OUT], fill=(30, 30, 30))
    draw.text((4, H_OUT - LABEL_H + 3), title, fill=(220, 220, 220))
    return img


def make_scatter_panel(
    density: np.ndarray,
    screen_xy: np.ndarray,
    visible: np.ndarray,
    values: np.ndarray,
    title: str,
) -> Image.Image:
    dn = _normalise(density)
    bg = np.array(
        Image.fromarray(_apply_colormap_hot(dn)).resize((W_OUT, H_OUT), Image.BILINEAR)
    ).copy()
    bg = (bg * 0.45).astype(np.uint8)
    img = Image.fromarray(bg)
    draw = ImageDraw.Draw(img)

    vis_xy = screen_xy[visible]
    vis_val = values[visible]
    vmax = float(vis_val.max()) if vis_val.size and vis_val.max() > 0 else 1.0

    for (sx, sy), v in zip(vis_xy, vis_val):
        if not (0.0 <= sx <= 1.0 and 0.0 <= sy <= 1.0):
            continue
        px = int(sx * (W_OUT - 1))
        py = int(sy * (H_OUT - 1))
        col = _apply_colormap_plasma(float(v) / vmax)
        draw.ellipse([px - 1, py - 1, px + 1, py + 1], fill=col)

    draw.rectangle([0, H_OUT - LABEL_H, W_OUT, H_OUT], fill=(30, 30, 30))
    draw.text((4, H_OUT - LABEL_H + 3), title, fill=(220, 220, 220))
    return img


def hstack_images(images: list[Image.Image], gap: int = 4) -> Image.Image:
    w = sum(im.width for im in images) + gap * (len(images) - 1)
    h = max(im.height for im in images)
    out = Image.new("RGB", (w, h), (20, 20, 20))
    x = 0
    for im in images:
        out.paste(im, (x, 0))
        x += im.width + gap
    return out


def add_header(image: Image.Image, text: str) -> Image.Image:
    out = Image.new("RGB", (image.width, image.height + HEADER_H), (20, 20, 20))
    out.paste(image, (0, HEADER_H))
    draw = ImageDraw.Draw(out)
    draw.rectangle([0, 0, image.width, HEADER_H], fill=(18, 18, 18))
    draw.text((6, 5), text, fill=(235, 235, 235))
    return out


def select_frame_subset(sorted_frames: list[int], max_frames: int | None) -> list[int]:
    if max_frames is None or max_frames <= 0 or len(sorted_frames) <= max_frames:
        return sorted_frames
    idx = np.linspace(0, len(sorted_frames) - 1, max_frames, dtype=int)
    seen: set[int] = set()
    chosen: list[int] = []
    for i in idx.tolist():
        fr = sorted_frames[i]
        if fr not in seen:
            chosen.append(fr)
            seen.add(fr)
    return chosen


def deposit_bilinear_batch(hist: np.ndarray, x: np.ndarray, y: np.ndarray) -> None:
    x = np.clip(x.astype(np.float64), 0.0, IMG_W - 1.0)
    y = np.clip(y.astype(np.float64), 0.0, IMG_H - 1.0)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = np.minimum(x0 + 1, IMG_W - 1)
    y1 = np.minimum(y0 + 1, IMG_H - 1)
    dx = x - x0
    dy = y - y0
    np.add.at(hist, (y0, x0), (1.0 - dx) * (1.0 - dy))
    np.add.at(hist, (y0, x1), dx * (1.0 - dy))
    np.add.at(hist, (y1, x0), (1.0 - dx) * dy)
    np.add.at(hist, (y1, x1), dx * dy)


def world_to_screen(points_w: np.ndarray, view_matrix: np.ndarray, proj_mat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ones = np.ones((len(points_w), 1), dtype=np.float64)
    pts_h = np.hstack([points_w, ones])
    cam = (view_matrix @ pts_h.T).T
    clip = (proj_mat @ cam.T).T
    w = clip[:, 3]
    safe_w = np.where(np.abs(w) > 1e-12, w, 1e-12)
    ndc_x = clip[:, 0] / safe_w
    ndc_y = clip[:, 1] / safe_w
    screen_x = (ndc_x + 1.0) * 0.5
    screen_y = (1.0 - ndc_y) * 0.5
    return np.stack([screen_x, screen_y], axis=1), w


def frame_cone_contributions(
    xmesh: trimesh.Trimesh,
    camera_data: dict,
    batch: FrameGazeBatch,
    proj_mat: np.ndarray,
    sigma_deg: float,
    radius_sigma_mult: float,
) -> tuple[np.ndarray, np.ndarray]:
    face_sal = np.zeros(len(xmesh.faces), dtype=np.float64)
    origins, dirs = screen_to_rays(camera_data, batch.x_norm, batch.y_norm, proj_mat)
    locs, idx_ray, _idx_tri = xmesh.ray.intersects_location(
        ray_origins=origins,
        ray_directions=dirs,
        multiple_hits=False,
    )
    if len(locs) == 0:
        return face_sal, np.empty((0, 3), dtype=np.float64)

    hit_pts = np.asarray(locs, dtype=np.float64)
    origins_at_hit = origins[np.asarray(idx_ray, dtype=np.int64)]
    depths = np.linalg.norm(hit_pts - origins_at_hit, axis=1)
    sigma_world = np.maximum(depths * math.tan(math.radians(sigma_deg)), 1e-6)

    face_centroids_w = np.asarray(xmesh.triangles_center, dtype=np.float64)
    ftree = cKDTree(face_centroids_w)
    for pt, sigma in zip(hit_pts, sigma_world):
        idxs = ftree.query_ball_point(pt, r=radius_sigma_mult * sigma)
        if not idxs:
            idxs = [int(ftree.query(pt)[1])]
        idxs_arr = np.asarray(idxs, dtype=np.int64)
        local_faces = face_centroids_w[idxs_arr]
        weights = np.exp(-0.5 * np.sum((local_faces - pt) ** 2, axis=1) / sigma**2)
        face_sal[idxs_arr] += weights
    return face_sal, hit_pts


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_label = f"MeshMamba/{args.texture_type}"
    output_stem = f"{args.model}__{METHOD_NAME}"

    paths = resolve_model_paths(args)
    with paths["json"].open("r", encoding="utf-8") as f:
        camera_data = json.load(f)

    print(f"DATASET: {dataset_label}")
    print(f"MODEL  : {args.model}")
    print(f"METHOD : {METHOD_NAME}")
    print(f"OBJ    : {paths['obj']}")
    print(f"GT     : {paths['gt']}")
    print(f"CSV    : {paths['csv']}")
    print(f"JSON   : {paths['json']}")

    mesh = trimesh.load(str(paths["obj"]), process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)
    if isinstance(mesh, (list, tuple)):
        mesh = trimesh.util.concatenate([m for m in mesh if isinstance(m, trimesh.Trimesh)])
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected Trimesh-compatible OBJ, got {type(mesh)}")

    gt = np.loadtxt(paths["gt"])
    if len(gt) != len(mesh.faces):
        raise SystemExit(f"GT face count mismatch: GT has {len(gt)} entries, mesh has {len(mesh.faces)} faces.")
    gt_norm = _normalise(gt)

    gaze_batches, stats = load_gaze_batches(
        paths["csv"],
        fps=int(camera_data["video_info"]["fps"]),
        total_frames=int(camera_data["video_info"]["total_frames"]),
    )
    frames_list = camera_data["frames"]
    all_gaze_frames = sorted(gaze_batches.keys())
    frames_to_process = set(select_frame_subset(all_gaze_frames, args.max_frames))
    print(
        f"Frames with gaze: {len(gaze_batches)}  |  total gaze points: {stats['num_points']}"
        f"  |  processed frames: {len(frames_to_process)}"
    )

    proj_mat, _ = resolve_projection_matrix(
        camera_data,
        override_fov_deg=args.override_fov_deg,
        projection_fov_mode=args.projection_fov_mode,
    )
    view_matrix = np.asarray(camera_data["camera_static"]["view_matrix"], dtype=np.float64).reshape(4, 4)
    camera_world = np.linalg.inv(view_matrix)[:3, 3]

    cone_sal = np.zeros(len(mesh.faces), dtype=np.float64)
    frame_data: dict[int, dict[str, np.ndarray | int]] = {}

    for frame, batch in gaze_batches.items():
        if frame not in frames_to_process:
            continue
        n = int(batch.x_norm.size)
        if n == 0 or frame >= len(frames_list):
            continue

        hist = np.zeros((IMG_H, IMG_W), dtype=np.float64)
        deposit_bilinear_batch(hist, batch.x_norm * (IMG_W - 1), batch.y_norm * (IMG_H - 1))
        density = gaussian_filter(hist, sigma=args.sigma_px, mode="constant")
        density_sum = float(density.sum())
        if density_sum > 0.0:
            density /= density_sum

        rot_z = float(frames_list[frame]["rotation_z_radians"])
        xmesh = mesh.copy()
        xmesh.vertices = apply_model_transform(
            mesh.vertices,
            camera_data,
            rot_z,
            args.recenter_to_bbox_center,
            args.base_rotate_z_deg,
            args.extra_rotate_x_deg,
            args.extra_rotate_y_deg,
            args.transform_order,
        )

        frame_sal, _hit_pts = frame_cone_contributions(
            xmesh,
            camera_data,
            batch,
            proj_mat,
            args.sigma_deg,
            args.radius_sigma_mult,
        )
        cone_sal += frame_sal

        face_centroids_w = np.asarray(xmesh.triangles_center, dtype=np.float64)
        face_normals_w = np.asarray(xmesh.face_normals, dtype=np.float64)
        screen_xy, w_clip = world_to_screen(face_centroids_w, view_matrix, proj_mat)
        behind = w_clip <= 0
        to_cam = camera_world[None, :] - face_centroids_w
        front = np.einsum("ij,ij->i", face_normals_w, to_cam) > 0.0
        visible = (~behind) & front

        frame_data[frame] = {
            "density": density.copy(),
            "screen_xy": screen_xy.copy(),
            "visible": visible.copy(),
            "sample": frame_sal.copy(),
            "gaze_x": batch.x_norm.copy(),
            "gaze_y": batch.y_norm.copy(),
            "n": n,
        }

    pred_norm = _normalise(cone_sal)
    sorted_frames = sorted(frame_data.keys())
    if not sorted_frames:
        raise SystemExit("No valid processed frames found in the CSV.")

    if args.preview_frames:
        chosen = args.preview_frames
    else:
        k = len(sorted_frames)
        chosen = [sorted_frames[k // 4], sorted_frames[k // 2], sorted_frames[3 * k // 4]]

    for fr in chosen:
        if fr not in frame_data:
            print(f"Frame {fr} not in gaze data, skipping.")
            continue

        fd = frame_data[fr]
        density = fd["density"]
        visible = fd["visible"]
        screen_xy = fd["screen_xy"]

        p1 = make_density_panel(density, f"Gaze density  frame={fr}  n={fd['n']}")
        d1 = ImageDraw.Draw(p1)
        for gx, gy in zip(fd["gaze_x"], fd["gaze_y"]):
            px = int(gx * (W_OUT - 1))
            py = int(gy * (H_OUT - 1))
            d1.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(0, 255, 255))

        p2 = make_scatter_panel(
            density,
            screen_xy,
            visible,
            fd["sample"],
            "Predicted cone saliency (face centroids)",
        )
        p3 = make_scatter_panel(
            density,
            screen_xy,
            visible,
            gt_norm,
            "GT saliency (face centroids)",
        )

        row = hstack_images([p1, p2, p3])
        row = add_header(
            row,
            f"dataset={dataset_label} | model={args.model} | method={METHOD_NAME} | frame={fr:04d}",
        )
        out = args.output_dir / f"{output_stem}__frame{fr:04d}.png"
        row.save(out)
        print(f"Saved: {out}")

    mid_fr = sorted_frames[len(sorted_frames) // 2]
    fd_mid = frame_data[mid_fr]
    p_pred = make_scatter_panel(
        np.zeros((IMG_H, IMG_W)),
        fd_mid["screen_xy"],
        fd_mid["visible"],
        pred_norm,
        "Predicted cone — accumulated",
    )
    p_gt = make_scatter_panel(
        np.zeros((IMG_H, IMG_W)),
        fd_mid["screen_xy"],
        fd_mid["visible"],
        gt_norm,
        "GT saliency",
    )
    summary = hstack_images([p_pred, p_gt])
    summary = add_header(
        summary,
        f"dataset={dataset_label} | model={args.model} | method={METHOD_NAME} | summary=accumulated_vs_gt",
    )
    out_summary = args.output_dir / f"{output_stem}__summary.png"
    summary.save(out_summary)
    print(f"Saved summary: {out_summary}")
    print(f"\nAll images in: {args.output_dir}")


if __name__ == "__main__":
    main()

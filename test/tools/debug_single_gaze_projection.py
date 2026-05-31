#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class GazePoint:
    row_index: int
    participation_id: str
    timestamp: float
    x_norm: float
    y_norm: float
    data_fps: str | None


@dataclass(frozen=True)
class HitResult:
    point: GazePoint
    frame_index: int
    json_frame_timestamp: float
    hit_point_world: np.ndarray
    hit_face_index: int
    ray_origin: np.ndarray
    ray_direction: np.ndarray
    pixel_error: float
    reprojected_xy_px: np.ndarray
    gaze_xy_px: np.ndarray


def _env_path(name: str, default: str | None = None) -> Path:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"Missing path env var: {name}")
    return Path(value)


def _candidate_model_names(model: str) -> list[str]:
    raw = model.strip()
    variants = [raw, raw.replace("_", "-"), raw.replace("-", "_")]
    stripped = re.sub(r"([_-])l\d+$", "", raw, flags=re.IGNORECASE)
    if stripped != raw:
        variants.extend([stripped, stripped.replace("_", "-"), stripped.replace("-", "_")])
    out: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = variant.lower()
        if key not in seen:
            out.append(variant)
            seen.add(key)
    return out


def _casefold_files(directory: Path, suffix: str) -> dict[str, Path]:
    return {
        path.name.lower(): path
        for path in sorted(directory.glob(f"*{suffix}"))
        if path.is_file()
    }


def _resolve_file(directory: Path, names: list[str], suffix: str) -> Path:
    index = _casefold_files(directory, suffix)
    for name in names:
        path = index.get(f"{name}{suffix}".lower())
        if path is not None:
            return path
    tried = ", ".join(f"{name}{suffix}" for name in names)
    raise FileNotFoundError(f"No file found in {directory}; tried: {tried}")


def resolve_meshmamba_non_texture_paths(model: str) -> dict[str, Path]:
    dataset_root = _env_path("REPROJECT_DATASET_MESHMAMBA_ROOT")
    csv_root = _env_path("REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT")
    json_root = _env_path("REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT")
    video_root = _env_path("REPROJECT_VIDEO_MESHMAMBA_NON_TEXTURE_ROOT")

    names = _candidate_model_names(model)
    mesh_root = dataset_root / "MeshFile" / "non_texture"
    dir_index = {path.name.lower(): path for path in mesh_root.iterdir() if path.is_dir()}
    model_dir = None
    for name in names:
        model_dir = dir_index.get(name.lower())
        if model_dir is not None:
            break
    if model_dir is None:
        raise FileNotFoundError(f"No MeshMamba model directory for {model} in {mesh_root}")

    return {
        "obj": _resolve_file(model_dir, names, ".obj"),
        "csv": _resolve_file(csv_root, names, ".csv"),
        "json": _resolve_file(json_root, [f"MeshMamba_non_texture_{name}" for name in names], ".json"),
        "video": _resolve_file(video_root, [f"MeshMamba_non_texture_{name}" for name in names], ".mp4"),
    }


def build_projection_matrix_from_fov(
    fov_deg: float,
    aspect_ratio: float,
    clip_start: float,
    clip_end: float,
) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    near = float(clip_start)
    far = float(clip_end)
    return np.asarray(
        [
            [f / aspect_ratio, 0.0, 0.0, 0.0],
            [0.0, f, 0.0, 0.0],
            [0.0, 0.0, -(far + near) / (far - near), -(2.0 * far * near) / (far - near)],
            [0.0, 0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )


def apply_model_transform(
    vertices: np.ndarray,
    metadata: dict[str, Any],
    rotation_z_rad: float,
    *,
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

    if recenter_to_bbox_center:
        v -= bbox_center

    scale = np.asarray(metadata["model_static"]["scale"], dtype=np.float64)
    v *= scale

    if transform_order == "eval":
        v = rotate_z(v, math.radians(base_rotate_z_deg))
        v = rotate_z(v, rotation_z_rad)
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
    elif transform_order == "blender_rig":
        # Blender canonical preview uses a parent rig for per-frame Z rotation.
        # Child object rotations happen before the parent rig rotation in world space.
        v = rotate_x(v, extra_rotate_x_deg)
        v = rotate_y(v, extra_rotate_y_deg)
        v = rotate_z(v, math.radians(base_rotate_z_deg))
        v = rotate_z(v, rotation_z_rad)
    else:
        raise ValueError(f"Unsupported transform order: {transform_order}")

    v += np.asarray(metadata["model_static"]["location"], dtype=np.float64)
    return v


def screen_to_ray(
    metadata: dict[str, Any],
    x_norm: float,
    y_norm: float,
    projection_matrix: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    ndc_x = x_norm * 2.0 - 1.0
    ndc_y = -(y_norm * 2.0 - 1.0)
    ndc_near = np.asarray([ndc_x, ndc_y, -1.0, 1.0], dtype=np.float64)
    ndc_far = np.asarray([ndc_x, ndc_y, 1.0, 1.0], dtype=np.float64)

    view_matrix = np.asarray(metadata["camera_static"]["view_matrix"], dtype=np.float64).reshape(4, 4)
    inv_proj = np.linalg.inv(projection_matrix)
    inv_view = np.linalg.inv(view_matrix)

    cam_near = inv_proj @ ndc_near
    cam_near /= cam_near[3]
    cam_far = inv_proj @ ndc_far
    cam_far /= cam_far[3]

    world_near = inv_view @ cam_near
    world_far = inv_view @ cam_far
    origin = world_near[:3]
    direction = world_far[:3] - world_near[:3]
    direction /= np.linalg.norm(direction)
    return origin, direction


def world_to_screen_px(
    points_world: np.ndarray,
    metadata: dict[str, Any],
    projection_matrix: np.ndarray,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    points_world = np.asarray(points_world, dtype=np.float64).reshape(-1, 3)
    view_matrix = np.asarray(metadata["camera_static"]["view_matrix"], dtype=np.float64).reshape(4, 4)
    pts_h = np.hstack([points_world, np.ones((len(points_world), 1), dtype=np.float64)])
    cam = (view_matrix @ pts_h.T).T
    clip = (projection_matrix @ cam.T).T
    w = clip[:, 3]
    safe_w = np.where(np.abs(w) > 1e-12, w, 1e-12)
    ndc_x = clip[:, 0] / safe_w
    ndc_y = clip[:, 1] / safe_w
    screen_x = (ndc_x + 1.0) * 0.5 * (width - 1)
    screen_y = (1.0 - ndc_y) * 0.5 * (height - 1)
    return np.stack([screen_x, screen_y], axis=1), cam[:, :3]


def nearest_json_frame(metadata: dict[str, Any], timestamp: float) -> int:
    frame_times = np.asarray([float(frame["timestamp"]) for frame in metadata["frames"]], dtype=np.float64)
    return int(np.argmin(np.abs(frame_times - float(timestamp))))


def load_gaze_points(csv_path: Path) -> list[GazePoint]:
    points: list[GazePoint] = []
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_index, row in enumerate(reader):
            gaze = ast.literal_eval(row["data_gazes"])
            ts = gaze.get("t", [])
            xs = gaze.get("x", [])
            ys = gaze.get("y", [])
            for t, x, y in zip(ts, xs, ys):
                x_f = float(x)
                y_f = float(y)
                if 0.0 <= x_f <= 1.0 and 0.0 <= y_f <= 1.0:
                    points.append(
                        GazePoint(
                            row_index=row_index,
                            participation_id=str(row.get("participation_id", "")),
                            timestamp=float(t),
                            x_norm=x_f,
                            y_norm=y_f,
                            data_fps=row.get("data_fps"),
                        )
                    )
    return points


def sorted_candidate_points(points: list[GazePoint], duration: float) -> list[GazePoint]:
    midpoint = 0.5 * duration

    def score(point: GazePoint) -> float:
        center_dist = math.hypot(point.x_norm - 0.5, point.y_norm - 0.5)
        time_dist = abs(point.timestamp - midpoint) / max(duration, 1e-6)
        return center_dist * 2.0 + time_dist

    return sorted(points, key=score)


def transformed_mesh_for_frame(
    mesh: trimesh.Trimesh,
    metadata: dict[str, Any],
    frame_index: int,
    *,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    transform_order: str,
) -> trimesh.Trimesh:
    rotation_z = float(metadata["frames"][frame_index]["rotation_z_radians"])
    xmesh = mesh.copy()
    xmesh.vertices = apply_model_transform(
        np.asarray(mesh.vertices, dtype=np.float64),
        metadata,
        rotation_z,
        recenter_to_bbox_center=recenter_to_bbox_center,
        base_rotate_z_deg=base_rotate_z_deg,
        extra_rotate_x_deg=extra_rotate_x_deg,
        extra_rotate_y_deg=extra_rotate_y_deg,
        transform_order=transform_order,
    )
    return xmesh


def find_hit_for_point(
    mesh: trimesh.Trimesh,
    metadata: dict[str, Any],
    point: GazePoint,
    projection_matrix: np.ndarray,
    *,
    recenter_to_bbox_center: bool,
    base_rotate_z_deg: float,
    extra_rotate_x_deg: float,
    extra_rotate_y_deg: float,
    transform_order: str,
    width: int,
    height: int,
) -> HitResult | None:
    frame_index = nearest_json_frame(metadata, point.timestamp)
    xmesh = transformed_mesh_for_frame(
        mesh,
        metadata,
        frame_index,
        recenter_to_bbox_center=recenter_to_bbox_center,
        base_rotate_z_deg=base_rotate_z_deg,
        extra_rotate_x_deg=extra_rotate_x_deg,
        extra_rotate_y_deg=extra_rotate_y_deg,
        transform_order=transform_order,
    )
    origin, direction = screen_to_ray(metadata, point.x_norm, point.y_norm, projection_matrix)
    locs, _idx_ray, idx_tri = xmesh.ray.intersects_location(
        ray_origins=origin.reshape(1, 3),
        ray_directions=direction.reshape(1, 3),
        multiple_hits=False,
    )
    if len(locs) == 0:
        return None

    hit_world = np.asarray(locs[0], dtype=np.float64)
    hit_face = int(idx_tri[0])
    reprojected_xy, _ = world_to_screen_px(hit_world.reshape(1, 3), metadata, projection_matrix, width, height)
    gaze_xy = np.asarray([point.x_norm * (width - 1), point.y_norm * (height - 1)], dtype=np.float64)
    pixel_error = float(np.linalg.norm(reprojected_xy[0] - gaze_xy))
    return HitResult(
        point=point,
        frame_index=frame_index,
        json_frame_timestamp=float(metadata["frames"][frame_index]["timestamp"]),
        hit_point_world=hit_world,
        hit_face_index=hit_face,
        ray_origin=origin,
        ray_direction=direction,
        pixel_error=pixel_error,
        reprojected_xy_px=reprojected_xy[0],
        gaze_xy_px=gaze_xy,
    )


def extract_video_frame(video_path: Path, timestamp: float, output_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to extract the source video frame")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{timestamp:.6f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)


def contour_from_mask(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask.astype(bool), ((1, 1), (1, 1)), mode="constant", constant_values=False)
    center = padded[1:-1, 1:-1]
    up = padded[:-2, 1:-1]
    down = padded[2:, 1:-1]
    left = padded[1:-1, :-2]
    right = padded[1:-1, 2:]
    interior = center & up & down & left & right
    return center & (~interior)


def estimate_background_rgb(image_rgb: np.ndarray) -> np.ndarray:
    h, w, _ = image_rgb.shape
    patch = max(1, min(24, h // 4, w // 4))
    corners = np.concatenate(
        [
            image_rgb[:patch, :patch].reshape(-1, 3),
            image_rgb[:patch, w - patch :].reshape(-1, 3),
            image_rgb[h - patch :, :patch].reshape(-1, 3),
            image_rgb[h - patch :, w - patch :].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(corners, axis=0)


def extract_video_mask(image: Image.Image, threshold: float) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    bg = estimate_background_rgb(rgb)
    dist = np.linalg.norm(rgb - bg.reshape(1, 1, 3), axis=2)
    return dist > threshold


def mask_centroid(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return float("nan"), float("nan")
    return float(xs.mean()), float(ys.mean())


def mask_bbox(mask: np.ndarray) -> tuple[int, int]:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return 0, 0
    return int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def score_masks(video_mask: np.ndarray, preview_mask: np.ndarray) -> dict[str, float]:
    inter = float(np.logical_and(video_mask, preview_mask).sum())
    union = float(np.logical_or(video_mask, preview_mask).sum())
    iou = inter / union if union > 0 else 0.0

    vx, vy = mask_centroid(video_mask)
    px, py = mask_centroid(preview_mask)
    h, w = video_mask.shape
    diag = math.hypot(w, h)
    centroid_error = math.hypot(px - vx, py - vy) / diag if np.isfinite([vx, vy, px, py]).all() else 1.0

    vw, vh = mask_bbox(video_mask)
    pw, ph = mask_bbox(preview_mask)
    size_error = (abs(pw - vw) + abs(ph - vh)) / max(1.0, float(vw + vh))
    return {
        "iou": float(iou),
        "centroid_error_norm": float(centroid_error),
        "size_error_norm": float(size_error),
        "video_bbox_width": int(vw),
        "video_bbox_height": int(vh),
        "preview_bbox_width": int(pw),
        "preview_bbox_height": int(ph),
        "intersection_pixels": int(inter),
        "union_pixels": int(union),
    }


def make_mask_compare_image(image: Image.Image, video_mask: np.ndarray, preview_mask: np.ndarray) -> Image.Image:
    out = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
    video_only = video_mask & (~preview_mask)
    preview_only = preview_mask & (~video_mask)
    overlap = video_mask & preview_mask
    out[video_only] = np.asarray([230, 40, 40], dtype=np.uint8)
    out[preview_only] = np.asarray([20, 180, 230], dtype=np.uint8)
    out[overlap] = np.asarray([245, 245, 245], dtype=np.uint8)

    video_edge = contour_from_mask(video_mask)
    preview_edge = contour_from_mask(preview_mask)
    out[video_edge] = np.asarray([255, 0, 0], dtype=np.uint8)
    out[preview_edge] = np.asarray([0, 255, 255], dtype=np.uint8)
    return Image.fromarray(out, mode="RGB")


def draw_mesh_overlay(
    image: Image.Image,
    xmesh: trimesh.Trimesh,
    metadata: dict[str, Any],
    projection_matrix: np.ndarray,
) -> tuple[Image.Image, np.ndarray]:
    width, height = image.size
    vertices = np.asarray(xmesh.vertices, dtype=np.float64)
    faces = np.asarray(xmesh.faces, dtype=np.int64)
    screen_xy, verts_cam = world_to_screen_px(vertices, metadata, projection_matrix, width, height)
    valid_vertices = verts_cam[:, 2] < -1e-8
    valid_faces = np.all(valid_vertices[faces], axis=1)
    faces_valid = faces[valid_faces]
    if len(faces_valid) == 0:
        return image.copy(), np.zeros((height, width), dtype=bool)

    polygons = screen_xy[faces_valid]
    depth = verts_cam[faces_valid, 2].mean(axis=1)
    order = np.argsort(depth)
    polygons = polygons[order]

    mask_img = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask_img)
    for poly in polygons:
        coords = [tuple(map(float, p)) for p in poly]
        mask_draw.polygon(coords, fill=255)

    mask = np.asarray(mask_img, dtype=np.uint8) > 0
    contour = contour_from_mask(mask)

    out = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
    tint = np.asarray([30, 170, 230], dtype=np.float32)
    alpha = 0.22
    out[mask] = np.clip(out[mask].astype(np.float32) * (1.0 - alpha) + tint * alpha, 0, 255).astype(np.uint8)
    out[contour] = np.asarray([255, 210, 0], dtype=np.uint8)
    return Image.fromarray(out, mode="RGB"), mask


def draw_debug_markers(
    image: Image.Image,
    hit: HitResult,
    xmesh: trimesh.Trimesh,
    metadata: dict[str, Any],
    projection_matrix: np.ndarray,
) -> Image.Image:
    out = image.convert("RGB")
    draw = ImageDraw.Draw(out, "RGBA")
    width, height = out.size

    face = np.asarray(xmesh.faces[hit.hit_face_index], dtype=np.int64)
    tri_world = np.asarray(xmesh.vertices[face], dtype=np.float64)
    tri_xy, _ = world_to_screen_px(tri_world, metadata, projection_matrix, width, height)
    draw.polygon([tuple(map(float, p)) for p in tri_xy], outline=(255, 255, 0, 230), fill=(255, 255, 0, 45))

    def dot(xy: np.ndarray, radius: int, fill: tuple[int, int, int, int], outline: tuple[int, int, int, int]) -> None:
        x, y = float(xy[0]), float(xy[1])
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=outline, width=3)

    dot(hit.gaze_xy_px, 10, (255, 0, 0, 210), (255, 255, 255, 255))
    dot(hit.reprojected_xy_px, 5, (0, 255, 80, 230), (0, 0, 0, 255))

    text_lines = [
        "red: CSV gaze point",
        "green: raycast hit reprojected to screen",
        f"participant={hit.point.participation_id}  t={hit.point.timestamp:.4f}s",
        f"json_frame={hit.frame_index}  json_t={hit.json_frame_timestamp:.4f}s",
        f"face={hit.hit_face_index}  pixel_error={hit.pixel_error:.4f}px",
    ]
    x0, y0 = 18, 18
    line_h = 19
    box_w = 620
    box_h = line_h * len(text_lines) + 14
    draw.rectangle((x0 - 8, y0 - 8, x0 + box_w, y0 + box_h), fill=(0, 0, 0, 150))
    for i, line in enumerate(text_lines):
        draw.text((x0, y0 + i * line_h), line, fill=(255, 255, 255, 255))
    return out


def build_projection_matrix(metadata: dict[str, Any], override_fov_deg: float | None) -> np.ndarray:
    camera = metadata["camera_static"]
    video = metadata["video_info"]
    if override_fov_deg is None:
        return np.asarray(camera["projection_matrix"], dtype=np.float64).reshape(4, 4)
    return build_projection_matrix_from_fov(
        fov_deg=override_fov_deg,
        aspect_ratio=float(video["aspect_ratio"]),
        clip_start=float(camera["clip_start"]),
        clip_end=float(camera["clip_end"]),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a single-gaze-point raycast debug preview.")
    parser.add_argument("--dataset", choices=["meshmamba_non_texture"], default="meshmamba_non_texture")
    parser.add_argument("--model", default="Starfruit_L3")
    parser.add_argument("--participant-id", default=None)
    parser.add_argument("--timestamp", type=float, default=None)
    parser.add_argument("--max-candidates", type=int, default=500)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--recenter-to-bbox-center", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--base-rotate-z-deg", type=float, default=0.0)
    parser.add_argument("--extra-rotate-x-deg", type=float, default=90.0)
    parser.add_argument("--extra-rotate-y-deg", type=float, default=0.0)
    parser.add_argument("--transform-order", choices=["eval", "blender_rig"], default="eval")
    parser.add_argument("--override-fov-deg", type=float, default=None)
    parser.add_argument("--video-mask-threshold", type=float, default=10.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = resolve_meshmamba_non_texture_paths(args.model)
    with paths["json"].open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    width = int(metadata["video_info"]["resolution_width"])
    height = int(metadata["video_info"]["resolution_height"])
    duration = float(metadata["video_info"]["duration_seconds"])
    projection_matrix = build_projection_matrix(metadata, args.override_fov_deg)
    mesh = trimesh.load(str(paths["obj"]), process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise SystemExit(f"Expected one Trimesh, got {type(mesh)}")

    all_points = load_gaze_points(paths["csv"])
    if args.participant_id is not None:
        all_points = [p for p in all_points if p.participation_id == str(args.participant_id)]
    if args.timestamp is not None:
        if not all_points:
            raise SystemExit("No gaze points remain after participant filter.")

        def timestamp_score(point: GazePoint) -> tuple[float, float]:
            center_dist = math.hypot(point.x_norm - 0.5, point.y_norm - 0.5)
            return abs(point.timestamp - args.timestamp), center_dist

        candidates = sorted(all_points, key=timestamp_score)[: max(1, args.max_candidates)]
    else:
        candidates = sorted_candidate_points(all_points, duration)[: max(1, args.max_candidates)]

    hit = None
    for point in candidates:
        hit = find_hit_for_point(
            mesh,
            metadata,
            point,
            projection_matrix,
            recenter_to_bbox_center=bool(args.recenter_to_bbox_center),
            base_rotate_z_deg=args.base_rotate_z_deg,
            extra_rotate_x_deg=args.extra_rotate_x_deg,
            extra_rotate_y_deg=args.extra_rotate_y_deg,
            transform_order=args.transform_order,
            width=width,
            height=height,
        )
        if hit is not None:
            break
    if hit is None:
        target = "central video time" if args.timestamp is None else f"timestamp {args.timestamp:.6f}"
        raise SystemExit(f"No mesh hit found near {target} in first {len(candidates)} candidate gaze points.")

    output_root = args.output_dir or (_env_path("REPROJECT_OUTPUT_ROOT") / "single_point_debug")
    fov_tag = "json_fov" if args.override_fov_deg is None else f"fov_{str(args.override_fov_deg).replace('.', 'p')}"
    output_dir = (
        output_root
        / args.dataset
        / args.model
        / args.transform_order
        / fov_tag
        / f"frame_{hit.frame_index:04d}_t_{hit.point.timestamp:.3f}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    video_frame_path = output_dir / "video_frame.png"
    extract_video_frame(paths["video"], hit.point.timestamp, video_frame_path)
    video_frame = Image.open(video_frame_path).convert("RGB")
    if video_frame.size != (width, height):
        video_frame = video_frame.resize((width, height), Image.Resampling.BILINEAR)
        video_frame.save(video_frame_path)

    xmesh = transformed_mesh_for_frame(
        mesh,
        metadata,
        hit.frame_index,
        recenter_to_bbox_center=bool(args.recenter_to_bbox_center),
        base_rotate_z_deg=args.base_rotate_z_deg,
        extra_rotate_x_deg=args.extra_rotate_x_deg,
        extra_rotate_y_deg=args.extra_rotate_y_deg,
        transform_order=args.transform_order,
    )
    mesh_overlay, mask = draw_mesh_overlay(video_frame, xmesh, metadata, projection_matrix)
    debug_overlay = draw_debug_markers(mesh_overlay, hit, xmesh, metadata, projection_matrix)
    video_mask = extract_video_mask(video_frame, threshold=args.video_mask_threshold)
    mask_metrics = score_masks(video_mask, mask)
    mask_compare = make_mask_compare_image(video_frame, video_mask=video_mask, preview_mask=mask)

    overlay_path = output_dir / "debug_overlay.png"
    mask_path = output_dir / "mesh_mask.png"
    video_mask_path = output_dir / "video_mask.png"
    mask_compare_path = output_dir / "mask_compare.png"
    debug_overlay.save(overlay_path)
    Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(mask_path)
    Image.fromarray((video_mask.astype(np.uint8) * 255), mode="L").save(video_mask_path)
    mask_compare.save(mask_compare_path)

    report = {
        "dataset": args.dataset,
        "model": args.model,
        "paths": {key: str(value) for key, value in paths.items()},
        "outputs": {
            "video_frame": str(video_frame_path),
            "debug_overlay": str(overlay_path),
            "mesh_mask": str(mask_path),
            "video_mask": str(video_mask_path),
            "mask_compare": str(mask_compare_path),
        },
        "transform": {
            "recenter_to_bbox_center": bool(args.recenter_to_bbox_center),
            "base_rotate_z_deg": float(args.base_rotate_z_deg),
            "extra_rotate_x_deg": float(args.extra_rotate_x_deg),
            "extra_rotate_y_deg": float(args.extra_rotate_y_deg),
            "transform_order": args.transform_order,
            "override_fov_deg": args.override_fov_deg,
        },
        "gaze_point": {
            "row_index": hit.point.row_index,
            "participation_id": hit.point.participation_id,
            "timestamp": hit.point.timestamp,
            "x_norm": hit.point.x_norm,
            "y_norm": hit.point.y_norm,
            "x_px": float(hit.gaze_xy_px[0]),
            "y_px": float(hit.gaze_xy_px[1]),
        },
        "frame_mapping": {
            "json_frame_index_0_based": hit.frame_index,
            "json_frame_number": int(metadata["frames"][hit.frame_index]["frame"]),
            "json_frame_timestamp": hit.json_frame_timestamp,
            "timestamp_delta_seconds": float(hit.point.timestamp - hit.json_frame_timestamp),
            "video_frame_extracted_at_timestamp": hit.point.timestamp,
        },
        "raycast": {
            "hit": True,
            "hit_face_index": hit.hit_face_index,
            "hit_point_world": hit.hit_point_world.astype(float).tolist(),
            "ray_origin_world": hit.ray_origin.astype(float).tolist(),
            "ray_direction_world": hit.ray_direction.astype(float).tolist(),
            "reprojected_x_px": float(hit.reprojected_xy_px[0]),
            "reprojected_y_px": float(hit.reprojected_xy_px[1]),
            "pixel_error_px": hit.pixel_error,
        },
        "mask_metrics": mask_metrics,
        "legend": {
            "red_dot": "CSV gaze point on extracted source video frame",
            "green_dot": "raycast hit point projected back to the same screen",
            "yellow_fill": "hit face",
            "cyan_fill": "projected mesh mask",
            "yellow_edges": "projected mesh contour",
            "mask_compare_red": "video-mask only",
            "mask_compare_cyan": "projected-mesh-mask only",
            "mask_compare_white": "intersection of video mask and projected mesh mask",
        },
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"Saved debug overlay: {overlay_path}")


if __name__ == "__main__":
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    main()

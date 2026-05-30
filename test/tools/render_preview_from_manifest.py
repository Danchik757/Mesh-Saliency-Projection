#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw


@dataclass
class MeshGeometry:
    vertices: np.ndarray
    faces: np.ndarray


def expand_path(raw: str | None) -> Path | None:
    if raw is None:
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if "$" in expanded:
        raise ValueError(f"Unresolved environment variable in path: {raw}")
    return Path(expanded)


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required_keys = ["dataset", "model", "obj_path", "json_path", "output_prefix"]
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise ValueError(f"Manifest {path} is missing keys: {missing}")
    return payload


def load_mesh(obj_path: Path) -> MeshGeometry:
    vertices: list[list[float]] = []
    faces: list[list[int]] = []

    for raw_line in obj_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("v "):
            parts = line.split()
            if len(parts) < 4:
                continue
            vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            continue
        if line.startswith("f "):
            tokens = line.split()[1:]
            indices: list[int] = []
            for token in tokens:
                head = token.split("/")[0]
                if not head:
                    continue
                idx = int(head)
                if idx < 0:
                    idx = len(vertices) + idx
                else:
                    idx = idx - 1
                indices.append(idx)
            if len(indices) < 3:
                continue
            if len(indices) == 3:
                faces.append(indices)
            else:
                for offset in range(1, len(indices) - 1):
                    faces.append([indices[0], indices[offset], indices[offset + 1]])

    if not vertices or not faces:
        raise ValueError(f"OBJ did not produce vertices/faces: {obj_path}")

    return MeshGeometry(
        vertices=np.asarray(vertices, dtype=np.float64),
        faces=np.asarray(faces, dtype=np.int64),
    )


def build_projection_matrix_from_fov_degrees(
    fov_degrees: float,
    aspect_ratio: float,
    clip_start: float,
    clip_end: float,
) -> np.ndarray:
    fov_radians = math.radians(float(fov_degrees))
    f = 1.0 / math.tan(fov_radians * 0.5)
    near = float(clip_start)
    far = float(clip_end)
    return np.asarray(
        [
            [f / float(aspect_ratio), 0.0, 0.0, 0.0],
            [0.0, f, 0.0, 0.0],
            [0.0, 0.0, -(far + near) / (far - near), -(2.0 * far * near) / (far - near)],
            [0.0, 0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )


def apply_projection_transform(
    vertices: np.ndarray,
    *,
    scale_xyz: np.ndarray,
    rotation_z_rad: float,
    translation_xyz: np.ndarray,
    recenter_to_bbox_center: bool = False,
    extra_rotate_x_deg: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    vertices = np.asarray(vertices, dtype=np.float64)
    scale_xyz = np.asarray(scale_xyz, dtype=np.float64).reshape(1, 3)
    translation_xyz = np.asarray(translation_xyz, dtype=np.float64).reshape(1, 3)

    bbox_center = 0.5 * (vertices.min(axis=0) + vertices.max(axis=0))
    transformed = vertices.copy()
    if recenter_to_bbox_center:
        transformed = transformed - bbox_center.reshape(1, 3)

    transformed = transformed * scale_xyz

    a = float(rotation_z_rad)
    ca = math.cos(a)
    sa = math.sin(a)
    x = transformed[:, 0]
    y = transformed[:, 1]
    z = transformed[:, 2]

    x2 = ca * x - sa * y
    y2 = sa * x + ca * y
    z2 = z

    rx = math.radians(float(extra_rotate_x_deg))
    if abs(rx) > 1e-12:
        crx = math.cos(rx)
        srx = math.sin(rx)
        y3 = crx * y2 - srx * z2
        z3 = srx * y2 + crx * z2
    else:
        y3 = y2
        z3 = z2

    out = np.stack([x2, y3, z3], axis=1)
    out = out + translation_xyz
    return out, bbox_center


def project_vertices(
    vertices_world: np.ndarray,
    metadata: dict[str, Any],
    projection_matrix: np.ndarray,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    view = np.asarray(metadata["camera_static"]["view_matrix"], dtype=np.float64).reshape(4, 4)

    verts_h = np.concatenate([vertices_world, np.ones((len(vertices_world), 1), dtype=np.float64)], axis=1)
    verts_cam = (view @ verts_h.T).T
    verts_clip = (projection_matrix @ verts_cam.T).T

    w = verts_clip[:, 3]
    valid = w > 1e-8
    ndc = np.zeros((len(vertices_world), 3), dtype=np.float64)
    ndc[valid] = verts_clip[valid, :3] / w[valid, None]

    screen_xy = np.empty((len(vertices_world), 2), dtype=np.float64)
    screen_xy[:, 0] = (ndc[:, 0] + 1.0) * 0.5 * (width - 1)
    screen_xy[:, 1] = (1.0 - (ndc[:, 1] + 1.0) * 0.5) * (height - 1)
    return screen_xy, verts_cam[:, :3], valid


def collect_frame_gaze_points(csv_path: Path, fps: int, target_frame: int, width: int, height: int) -> np.ndarray:
    df = pd.read_csv(csv_path)
    points: list[tuple[float, float]] = []
    for _, row in df.iterrows():
        gaze = ast.literal_eval(row["data_gazes"])
        for t, x, y in zip(gaze.get("t", []), gaze.get("x", []), gaze.get("y", [])):
            frame = int(math.floor(float(t) * fps))
            if frame != target_frame:
                continue
            points.append((float(x) * (width - 1), float(y) * (height - 1)))
    if not points:
        return np.zeros((0, 2), dtype=np.float64)
    return np.asarray(points, dtype=np.float64)


def render_preview(
    mesh: MeshGeometry,
    metadata: dict[str, Any],
    frame_idx: int,
    output_path: Path,
    *,
    width: int,
    height: int,
    recenter_to_bbox_center: bool = False,
    extra_rotate_x_deg: float = 0.0,
    override_fov_deg: float | None = None,
    gaze_points_xy: np.ndarray | None = None,
) -> dict[str, Any]:
    projection_matrix = (
        np.asarray(metadata["camera_static"]["projection_matrix"], dtype=np.float64).reshape(4, 4)
        if override_fov_deg is None
        else build_projection_matrix_from_fov_degrees(
            fov_degrees=float(override_fov_deg),
            aspect_ratio=float(metadata["video_info"]["aspect_ratio"]),
            clip_start=float(metadata["camera_static"]["clip_start"]),
            clip_end=float(metadata["camera_static"]["clip_end"]),
        )
    )
    transformed_vertices, bbox_center = apply_projection_transform(
        mesh.vertices,
        scale_xyz=np.asarray(metadata["model_static"]["scale"], dtype=np.float64),
        rotation_z_rad=float(metadata["frames"][frame_idx]["rotation_z_radians"]),
        translation_xyz=np.asarray(metadata["model_static"]["location"], dtype=np.float64),
        recenter_to_bbox_center=recenter_to_bbox_center,
        extra_rotate_x_deg=extra_rotate_x_deg,
    )
    screen_xy, verts_cam, valid_vertices = project_vertices(transformed_vertices, metadata, projection_matrix, width, height)
    faces = mesh.faces
    valid_faces = np.all(valid_vertices[faces], axis=1)
    faces = faces[valid_faces]
    if len(faces) == 0:
        raise RuntimeError("No visible faces remained after projection.")

    polygons = screen_xy[faces]
    depth = verts_cam[faces, 2].mean(axis=1)

    face_vertices_world = transformed_vertices[faces]
    face_centers = face_vertices_world.mean(axis=1)
    edge1 = face_vertices_world[:, 1, :] - face_vertices_world[:, 0, :]
    edge2 = face_vertices_world[:, 2, :] - face_vertices_world[:, 0, :]
    face_normals = np.cross(edge1, edge2)
    face_normals /= np.clip(np.linalg.norm(face_normals, axis=1, keepdims=True), 1e-12, None)
    camera_pos = np.asarray(metadata["camera_static"]["location"], dtype=np.float64)
    view_dirs = camera_pos[None, :] - face_centers
    view_dirs /= np.clip(np.linalg.norm(view_dirs, axis=1, keepdims=True), 1e-12, None)
    diffuse = np.clip(np.sum(face_normals * view_dirs, axis=1), 0.0, 1.0)

    base_color = np.array([0.18, 0.55, 0.86], dtype=np.float64)
    ambient = 0.20
    shade = ambient + 0.80 * diffuse
    face_colors = np.clip(base_color[None, :] * shade[:, None] + 0.05, 0.0, 1.0)

    order = np.argsort(depth)
    polygons = polygons[order]
    face_colors = face_colors[order]

    image = Image.new("RGBA", (width, height), (246, 247, 251, 255))
    draw = ImageDraw.Draw(image, "RGBA")

    bbox_min_x = width
    bbox_min_y = height
    bbox_max_x = -1
    bbox_max_y = -1

    for poly, color in zip(polygons, face_colors):
        rgba = tuple(int(round(c * 255.0)) for c in color) + (255,)
        coords = [tuple(map(float, p)) for p in poly]
        draw.polygon(coords, fill=rgba)
        xs = [p[0] for p in coords]
        ys = [p[1] for p in coords]
        bbox_min_x = min(bbox_min_x, int(math.floor(min(xs))))
        bbox_min_y = min(bbox_min_y, int(math.floor(min(ys))))
        bbox_max_x = max(bbox_max_x, int(math.ceil(max(xs))))
        bbox_max_y = max(bbox_max_y, int(math.ceil(max(ys))))

    if gaze_points_xy is not None and len(gaze_points_xy) > 0:
        radius = max(3.0, min(width, height) / 160.0)
        for x, y in gaze_points_xy:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(217, 4, 41, 120))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)

    coverage_width = max(0, bbox_max_x - bbox_min_x + 1)
    coverage_height = max(0, bbox_max_y - bbox_min_y + 1)
    return {
        "bbox_center_raw_obj": bbox_center.astype(float).tolist(),
        "bbox_min_x": int(bbox_min_x if bbox_max_x >= 0 else -1),
        "bbox_min_y": int(bbox_min_y if bbox_max_y >= 0 else -1),
        "bbox_max_x": int(bbox_max_x),
        "bbox_max_y": int(bbox_max_y),
        "bbox_width": int(coverage_width),
        "bbox_height": int(coverage_height),
        "coverage_ratio_bbox": float((coverage_width * coverage_height) / float(width * height)) if width and height else 0.0,
    }


def resolve_video_resolution(metadata: dict[str, Any], scale: float) -> tuple[int, int]:
    video_info = metadata["video_info"]
    width = int(video_info["resolution_width"])
    height = int(video_info["resolution_height"])
    scale = max(0.05, float(scale))
    return max(64, int(round(width * scale))), max(64, int(round(height * scale)))


def render_from_manifest(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    obj_path = expand_path(manifest["obj_path"])
    json_path = expand_path(manifest["json_path"])
    csv_path = expand_path(manifest.get("csv_path"))
    output_prefix = expand_path(manifest["output_prefix"])
    if obj_path is None or json_path is None or output_prefix is None:
        raise ValueError("Manifest paths must not be null")
    for path in [obj_path, json_path]:
        if not path.exists():
            raise FileNotFoundError(f"Missing required input: {path}")
    if bool(manifest.get("overlay_gaze", False)) and csv_path is not None and not csv_path.exists():
        raise FileNotFoundError(f"Overlay requested but CSV is missing: {csv_path}")

    mesh = load_mesh(obj_path)
    metadata = json.loads(json_path.read_text(encoding="utf-8"))
    total_frames = int(metadata["video_info"]["total_frames"])
    frame_idx = int(np.clip(int(manifest.get("frame_index", 0)), 0, total_frames - 1))
    width, height = resolve_video_resolution(metadata, float(manifest.get("resolution_scale", 1.0)))

    plain_path = output_prefix.with_suffix(".png")
    plain_stats = render_preview(
        mesh=mesh,
        metadata=metadata,
        frame_idx=frame_idx,
        output_path=plain_path,
        width=width,
        height=height,
        recenter_to_bbox_center=bool(manifest.get("recenter_to_bbox_center", False)),
        extra_rotate_x_deg=float(manifest.get("extra_rotate_x_deg", 0.0)),
        override_fov_deg=manifest.get("override_fov_deg"),
    )

    overlay_path = None
    overlay_points = 0
    if bool(manifest.get("overlay_gaze", False)) and csv_path is not None:
        gaze_points_xy = collect_frame_gaze_points(
            csv_path=csv_path,
            fps=int(metadata["video_info"]["fps"]),
            target_frame=frame_idx,
            width=width,
            height=height,
        )
        overlay_points = int(len(gaze_points_xy))
        overlay_path = output_prefix.parent / f"{output_prefix.name}_gaze.png"
        render_preview(
            mesh=mesh,
            metadata=metadata,
            frame_idx=frame_idx,
            output_path=overlay_path,
            width=width,
            height=height,
            recenter_to_bbox_center=bool(manifest.get("recenter_to_bbox_center", False)),
            extra_rotate_x_deg=float(manifest.get("extra_rotate_x_deg", 0.0)),
            override_fov_deg=manifest.get("override_fov_deg"),
            gaze_points_xy=gaze_points_xy,
        )

    report = {
        "manifest_path": str(manifest_path),
        "dataset": str(manifest["dataset"]),
        "model": str(manifest["model"]),
        "obj_path": str(obj_path),
        "json_path": str(json_path),
        "csv_path": None if csv_path is None else str(csv_path),
        "frame_index": frame_idx,
        "resolution_width": int(width),
        "resolution_height": int(height),
        "recenter_to_bbox_center": bool(manifest.get("recenter_to_bbox_center", False)),
        "extra_rotate_x_deg": float(manifest.get("extra_rotate_x_deg", 0.0)),
        "override_fov_deg": manifest.get("override_fov_deg"),
        "plain_preview": str(plain_path),
        "overlay_preview": None if overlay_path is None else str(overlay_path),
        "overlay_points": overlay_points,
        "plain_stats": plain_stats,
    }
    report_path = output_prefix.parent / f"{output_prefix.name}.report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a dataset preview from a JSON manifest.")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    report = render_from_manifest(manifest, manifest_path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

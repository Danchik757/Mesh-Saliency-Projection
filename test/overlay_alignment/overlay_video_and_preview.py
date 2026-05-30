#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def load_rgb(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def resize_preview_to_video(video: Image.Image, preview: Image.Image) -> Image.Image:
    if preview.size == video.size:
        return preview
    return preview.resize(video.size, Image.Resampling.BILINEAR)


def estimate_background_rgb(preview_rgb: np.ndarray) -> np.ndarray:
    h, w, _ = preview_rgb.shape
    patch = 24
    corners = np.concatenate(
        [
            preview_rgb[:patch, :patch].reshape(-1, 3),
            preview_rgb[:patch, w - patch :].reshape(-1, 3),
            preview_rgb[h - patch :, :patch].reshape(-1, 3),
            preview_rgb[h - patch :, w - patch :].reshape(-1, 3),
        ],
        axis=0,
    )
    return np.median(corners, axis=0)


def extract_object_mask(preview: Image.Image, threshold: float = 10.0) -> np.ndarray:
    rgb = np.asarray(preview.convert("RGB"), dtype=np.float32)
    bg = estimate_background_rgb(rgb)
    dist = np.linalg.norm(rgb - bg.reshape(1, 1, 3), axis=2)
    return dist > threshold


def contour_from_mask(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask.astype(bool), ((1, 1), (1, 1)), mode="constant", constant_values=False)
    center = padded[1:-1, 1:-1]
    up = padded[:-2, 1:-1]
    down = padded[2:, 1:-1]
    left = padded[1:-1, :-2]
    right = padded[1:-1, 2:]
    interior = center & up & down & left & right
    return center & (~interior)


def make_alpha_overlay(video: Image.Image, preview: Image.Image, mask: np.ndarray, alpha: float) -> Image.Image:
    video_rgb = np.asarray(video.convert("RGB"), dtype=np.float32)
    preview_rgb = np.asarray(preview.convert("RGB"), dtype=np.float32)
    a = np.where(mask, alpha, 0.0).astype(np.float32)[..., None]
    out = video_rgb * (1.0 - a) + preview_rgb * a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


def make_edge_overlay(video: Image.Image, contour: np.ndarray, edge_color: tuple[int, int, int]) -> Image.Image:
    out = np.asarray(video.convert("RGB")).copy()
    out[contour] = np.asarray(edge_color, dtype=np.uint8)
    return Image.fromarray(out, mode="RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Overlay a rendered preview over a source video frame.")
    parser.add_argument("--video-frame", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--output-alpha", type=Path, required=True)
    parser.add_argument("--output-edges", type=Path, required=True)
    parser.add_argument("--alpha", type=float, default=0.35)
    parser.add_argument("--mask-threshold", type=float, default=10.0)
    args = parser.parse_args()

    video = load_rgb(args.video_frame)
    preview = resize_preview_to_video(video, load_rgb(args.preview))

    mask = extract_object_mask(preview, threshold=args.mask_threshold)
    contour = contour_from_mask(mask)

    alpha_overlay = make_alpha_overlay(video, preview, mask=mask, alpha=args.alpha)
    edge_overlay = make_edge_overlay(video, contour=contour, edge_color=(220, 20, 60))

    args.output_alpha.parent.mkdir(parents=True, exist_ok=True)
    args.output_edges.parent.mkdir(parents=True, exist_ok=True)
    alpha_overlay.save(args.output_alpha)
    edge_overlay.save(args.output_edges)


if __name__ == "__main__":
    main()

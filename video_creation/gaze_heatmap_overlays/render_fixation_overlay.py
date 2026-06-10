#!/usr/bin/env python3
"""
Render gaze heatmap overlay from rc3 fixation JSON onto source video.

rc3 fixation format (one_turn_from_start_offset_0):
  List of N frames; each frame is a list of [x, y] absolute pixel coordinates
  recorded at 1920x1080. gaze[k] corresponds to video frame k.

Two modes:
  full_video_overlay          all N frames in the JSON (510 / 720)
  benchmark_one_turn_overlay  first TURN_FRAMES[dataset] frames (450 / 660),
                              matching the evaluator timing contract

Usage (single model):
  python video_creation/gaze_heatmap_overlays/render_fixation_overlay.py \\
    --fixation-json /path/to/participant_fixations_offset0_full_cleaned/3DVA_A380/fixations.json \\
    --video-path    /path/to/source_videos/3DVA_A380.mp4 \\
    --output-path   results/gaze_overlays/3DVA_A380_full.mp4 \\
    --mode          full_video_overlay
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

# Rendering deps (PIL, ffprobe/ffmpeg wrappers) — lazy so pure-logic tests work
_render_import_error: Exception | None = None
try:
    from PIL import Image

    try:
        _RESAMPLE = Image.Resampling.BILINEAR
    except AttributeError:
        _RESAMPLE = Image.BILINEAR  # type: ignore[attr-defined]
except ImportError as _exc:
    _render_import_error = _exc


# ── rc3 timing constants ───────────────────────────────────────────────────────

# Matches release_manifest.json turn_frames
TURN_FRAMES: dict[str, int] = {
    "3DVA": 450,
    "MeshMamba": 450,
    "SAL3D": 660,
}

# Absolute pixel resolution of rc3 fixation coordinates
FIXATION_RESOLUTION: tuple[int, int] = (1920, 1080)

MODES: tuple[str, ...] = ("full_video_overlay", "benchmark_one_turn_overlay")

# Models excluded from benchmark metrics (rc3 known_blockers)
DEFAULT_EXCLUDED: frozenset[str] = frozenset({"3DVA_jessi"})


# ── model key parsing ──────────────────────────────────────────────────────────

def parse_model_key(model_key: str) -> dict[str, str]:
    """Split fixation dir name into dataset / track / model components.

    Examples:
      3DVA_A380                          → {dataset: 3DVA, track: '', model: A380}
      SAL3D_bunny                        → {dataset: SAL3D, track: '', model: bunny}
      MeshMamba_non_texture_Starfruit_L3 → {dataset: MeshMamba, track: non_texture, model: Starfruit_L3}
    """
    if model_key.startswith("SAL3D_"):
        return {"dataset": "SAL3D", "track": "", "model": model_key[len("SAL3D_"):]}
    if model_key.startswith("3DVA_"):
        return {"dataset": "3DVA", "track": "", "model": model_key[len("3DVA_"):]}
    if model_key.startswith("MeshMamba_non_texture_"):
        return {"dataset": "MeshMamba", "track": "non_texture",
                "model": model_key[len("MeshMamba_non_texture_"):]}
    if model_key.startswith("MeshMamba_rgb_texture_"):
        return {"dataset": "MeshMamba", "track": "rgb_texture",
                "model": model_key[len("MeshMamba_rgb_texture_"):]}
    if model_key.startswith("MeshMamba_"):
        return {"dataset": "MeshMamba", "track": "", "model": model_key[len("MeshMamba_"):]}
    raise ValueError(f"Cannot parse dataset from model_key: {model_key!r}")


def detect_dataset(model_key: str) -> str:
    return parse_model_key(model_key)["dataset"]


# ── fixation JSON loading ──────────────────────────────────────────────────────

def load_fixation_json(path: Path) -> list[list[list[int]]]:
    """Load fixations.json → list[frame] where frame = list of [x, y] pixel coords."""
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(
            f"Expected list in fixations.json, got {type(data).__name__}: {path}"
        )
    return data


# ── frame generator ────────────────────────────────────────────────────────────

class FixationJsonFrameGenerator:
    """Convert rc3 frame-indexed fixation points to a screen-space impulse map."""

    def __init__(
        self,
        frames: list[list[list[int]]],
        height: int,
        width: int,
        sigma_ref_px: float,
        fixation_resolution: tuple[int, int] = FIXATION_RESOLUTION,
    ) -> None:
        self.frames = frames
        self.height = height
        self.width = width
        self.sigma = sigma_ref_px / 1920.0 * width
        fix_res_w, fix_res_h = fixation_resolution
        self._scale_x = width / fix_res_w
        self._scale_y = height / fix_res_h

    def get_frame_impulse(self, frame_index: int) -> np.ndarray:
        sm = np.zeros((self.height, self.width), dtype=np.float32)
        if frame_index >= len(self.frames):
            return sm
        points = self.frames[frame_index]
        if not points:
            return sm
        weight = 1.0 / len(points)
        for px, py in points:
            j = max(0, min(self.width - 1, int(px * self._scale_x)))
            i = max(0, min(self.height - 1, int(py * self._scale_y)))
            sm[i, j] += weight
        return sm


# ── timing helper ──────────────────────────────────────────────────────────────

def n_frames_for_mode(mode: str, dataset: str, n_json_frames: int) -> int:
    if mode == "full_video_overlay":
        return n_json_frames
    return min(TURN_FRAMES[dataset], n_json_frames)


# ── pure image utilities (no PIL/pandas dependency) ───────────────────────────

def _normalize_map(sm_map: np.ndarray) -> np.ndarray:
    max_val = float(sm_map.max())
    if max_val <= 0.0:
        return np.zeros_like(sm_map, dtype=np.float32)
    return np.clip(sm_map.astype(np.float32) / max_val, 0.0, 1.0)


def _colorize_heatmap(heat: np.ndarray, max_opacity: float) -> tuple[np.ndarray, np.ndarray]:
    anchors = np.array([
        [0.00,   0,   0,   0],
        [0.20, 100,   0,   0],
        [0.45, 220,  20,   0],
        [0.75, 255, 180,   0],
        [1.00, 255, 255, 210],
    ], dtype=np.float32)
    flat = heat.reshape(-1)
    rgb = np.empty((flat.size, 3), dtype=np.float32)
    for c in range(3):
        rgb[:, c] = np.interp(flat, anchors[:, 0], anchors[:, c + 1])
    rgb = rgb.reshape(heat.shape + (3,))
    alpha = np.clip((heat - 0.05) / 0.95, 0.0, 1.0) ** 0.8 * max_opacity
    return rgb, alpha[..., None]


def _overlay_heatmap(frame: np.ndarray, heat: np.ndarray, max_opacity: float) -> np.ndarray:
    rgb, alpha = _colorize_heatmap(heat, max_opacity=max_opacity)
    blended = frame.astype(np.float32) * (1.0 - alpha) + rgb * alpha
    return np.clip(blended, 0, 255).astype(np.uint8)


# ── video I/O (requires ffmpeg; only called at render time) ───────────────────

def _probe_video(video_path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
         str(video_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    data = json.loads(result.stdout)
    vs = next(s for s in data["streams"] if s["codec_type"] == "video")
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    fps_n, fps_d = (int(p) for p in vs["avg_frame_rate"].split("/"))
    fps = fps_n / fps_d
    duration = float(vs.get("duration") or data["format"]["duration"])
    frame_count = int(vs.get("nb_frames") or math.floor(duration * fps + 0.5))
    return {
        "width": int(vs["width"]),
        "height": int(vs["height"]),
        "fps": fps,
        "duration": duration,
        "frame_count": frame_count,
        "has_audio": has_audio,
    }


def _build_decoder(video_path: Path) -> subprocess.Popen:
    return subprocess.Popen(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(video_path),
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-vsync", "0", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _build_encoder(
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    original_video_path: Path,
    keep_audio: bool,
) -> subprocess.Popen:
    cmd = [
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", f"{fps:.8f}", "-i", "-",
    ]
    if keep_audio:
        cmd += ["-i", str(original_video_path),
                "-map", "0:v:0", "-map", "1:a:0?", "-c:a", "copy", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", str(output_path)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def _upscale_map(sm_map: np.ndarray, width: int, height: int) -> np.ndarray:
    img = Image.fromarray((sm_map * 255.0).astype(np.uint8), mode="L")
    img = img.resize((width, height), _RESAMPLE)
    return np.asarray(img, dtype=np.float32) / 255.0


# ── main render function ───────────────────────────────────────────────────────

def render_fixation_overlay(
    fixation_json_path: Path,
    video_path: Path,
    output_path: Path,
    mode: str,
    sigma_ref_px: float = 40.0,
    map_width: int = 960,
    map_height: int = 540,
    max_opacity: float = 0.82,
    drop_audio: bool = False,
) -> dict:
    """Render gaze overlay for one model. Returns manifest dict."""
    if _render_import_error:
        raise RuntimeError(f"Missing rendering dependency: {_render_import_error}")
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode!r}. Choose: {MODES}")

    model_key = fixation_json_path.parent.name
    info = parse_model_key(model_key)
    dataset = info["dataset"]

    frames = load_fixation_json(fixation_json_path)
    n_json_frames = len(frames)
    n_render = n_frames_for_mode(mode, dataset, n_json_frames)

    meta = _probe_video(video_path)
    fps = float(meta["fps"])
    vw, vh = int(meta["width"]), int(meta["height"])

    generator = FixationJsonFrameGenerator(
        frames=frames,
        height=map_height,
        width=map_width,
        sigma_ref_px=sigma_ref_px,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    decoder = _build_decoder(video_path)
    encoder = _build_encoder(
        output_path=output_path,
        width=vw,
        height=vh,
        fps=fps,
        original_video_path=video_path,
        keep_audio=bool(meta["has_audio"]) and not drop_audio,
    )

    frame_size = vw * vh * 3
    frames_written = 0

    try:
        for frame_index in range(n_render):
            chunk = decoder.stdout.read(frame_size)
            if len(chunk) < frame_size:
                break
            frame = np.frombuffer(chunk, dtype=np.uint8).reshape((vh, vw, 3)).copy()
            sm_impulse = generator.get_frame_impulse(frame_index)
            sm_blurred = gaussian_filter(sm_impulse, sigma=generator.sigma, mode="constant")
            sm_norm = _normalize_map(sm_blurred)
            sm_up = _upscale_map(sm_norm, vw, vh)
            encoder.stdin.write(_overlay_heatmap(frame, sm_up, max_opacity=max_opacity).tobytes())
            frames_written += 1
            if (frame_index + 1) % 50 == 0 or frame_index + 1 == n_render:
                print(f"  frame {frame_index + 1}/{n_render}", flush=True)
    finally:
        if decoder.stdout:
            decoder.stdout.close()
        dec_err = decoder.stderr.read().decode("utf-8", errors="replace") if decoder.stderr else ""
        decoder.wait()
        if encoder.stdin:
            encoder.stdin.close()
        enc_err = encoder.stderr.read().decode("utf-8", errors="replace") if encoder.stderr else ""
        encoder.wait()

    if decoder.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed:\n{dec_err.strip()}")
    if encoder.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed:\n{enc_err.strip()}")
    if frames_written == 0:
        raise RuntimeError("No frames written to output video")

    return {
        "mode": mode,
        "dataset": dataset,
        "track": info["track"],
        "model": info["model"],
        "model_key": model_key,
        "fixation_format": "one_turn_from_start_offset_0",
        "fixation_json_path": str(fixation_json_path.resolve()),
        "video_path": str(video_path.resolve()),
        "output_path": str(output_path.resolve()),
        "n_json_frames": n_json_frames,
        "frame_count": frames_written,
        "fps": fps,
        "resolution": f"{vw}x{vh}",
        "internal_map_size": f"{map_width}x{map_height}",
        "sigma_ref_px": sigma_ref_px,
        "max_opacity": max_opacity,
        "crop_start_sec": 0.0,
        "crop_end_sec": 0.0,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Render rc3 fixation JSON gaze overlay on source video."
    )
    ap.add_argument("--fixation-json", type=Path, required=True,
                    help="fixations.json inside participant_fixations_offset0_full_cleaned/{model_key}/")
    ap.add_argument("--video-path", type=Path, required=True)
    ap.add_argument("--output-path", type=Path, required=True)
    ap.add_argument("--mode", choices=MODES, default="full_video_overlay")
    ap.add_argument("--sigma-ref-px", type=float, default=40.0)
    ap.add_argument("--map-width", type=int, default=960)
    ap.add_argument("--map-height", type=int, default=540)
    ap.add_argument("--max-opacity", type=float, default=0.82)
    ap.add_argument("--drop-audio", action="store_true")
    return ap


def main() -> None:
    args = _build_parser().parse_args()
    for p, name in [(args.fixation_json, "--fixation-json"), (args.video_path, "--video-path")]:
        if not p.exists():
            print(f"[ERROR] {name} not found: {p}", file=sys.stderr)
            sys.exit(1)
    result = render_fixation_overlay(
        fixation_json_path=args.fixation_json,
        video_path=args.video_path,
        output_path=args.output_path,
        mode=args.mode,
        sigma_ref_px=args.sigma_ref_px,
        map_width=args.map_width,
        map_height=args.map_height,
        max_opacity=args.max_opacity,
        drop_audio=args.drop_audio,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

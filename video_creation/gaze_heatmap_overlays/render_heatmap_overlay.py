#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.ndimage import gaussian_filter


try:
    RESAMPLE_BILINEAR = Image.Resampling.BILINEAR
except AttributeError:
    RESAMPLE_BILINEAR = Image.BILINEAR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render an aggregate gaze heatmap overlay video from a raw gaze CSV."
    )
    parser.add_argument("--csv-path", type=Path, required=True)
    parser.add_argument("--video-path", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument(
        "--sigma-ref-px",
        type=float,
        default=40.0,
        help="Reference Gaussian sigma in a 1920px-wide screen space.",
    )
    parser.add_argument(
        "--map-width",
        type=int,
        default=960,
        help="Internal heatmap width before resizing to video resolution.",
    )
    parser.add_argument(
        "--map-height",
        type=int,
        default=540,
        help="Internal heatmap height before resizing to video resolution.",
    )
    parser.add_argument(
        "--max-opacity",
        type=float,
        default=0.82,
        help="Maximum overlay opacity for the colorized heatmap.",
    )
    parser.add_argument(
        "--participant-ids",
        nargs="+",
        type=int,
        default=None,
        help="Optional subset of participant ids to keep. Default: all rows in the CSV.",
    )
    parser.add_argument(
        "--drop-audio",
        action="store_true",
        help="Do not copy the original audio track into the output video.",
    )
    return parser.parse_args()


def run_command(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")
    return result.stdout


def probe_video(video_path: Path) -> dict[str, object]:
    data = json.loads(
        run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(video_path),
            ]
        )
    )
    video_stream = next(stream for stream in data["streams"] if stream["codec_type"] == "video")
    audio_stream = next((stream for stream in data["streams"] if stream["codec_type"] == "audio"), None)
    fps_num, fps_den = (int(part) for part in video_stream["avg_frame_rate"].split("/"))
    fps = fps_num / fps_den
    duration = float(video_stream.get("duration") or data["format"]["duration"])
    frame_count = int(video_stream.get("nb_frames") or math.floor(duration * fps + 0.5))
    return {
        "width": int(video_stream["width"]),
        "height": int(video_stream["height"]),
        "fps": fps,
        "duration": duration,
        "frame_count": frame_count,
        "has_audio": audio_stream is not None,
    }


def load_observers_data(csv_path: Path, participant_ids: set[int] | None) -> list[dict[str, np.ndarray | int]]:
    df = pd.read_csv(csv_path)
    observers: list[dict[str, np.ndarray | int]] = []

    for _, row in df.iterrows():
        participant_id = int(row["participation_id"])
        if participant_ids is not None and participant_id not in participant_ids:
            continue

        gaze = ast.literal_eval(row["data_gazes"])
        t = np.asarray(gaze["t"], dtype=np.float64)
        x = np.asarray(gaze["x"], dtype=np.float64)
        y = np.asarray(gaze["y"], dtype=np.float64)

        if not (len(t) == len(x) == len(y)):
            continue

        valid = np.isfinite(t) & np.isfinite(x) & np.isfinite(y)
        t = t[valid]
        x = np.clip(x[valid], 0.0, 1.0)
        y = np.clip(y[valid], 0.0, 1.0)
        if len(t) == 0:
            continue

        order = np.argsort(t, kind="stable")
        t = t[order]
        x = x[order]
        y = y[order]
        unique_mask = np.concatenate(([True], np.diff(t) > 0))

        observers.append(
            {
                "t": t[unique_mask],
                "x": x[unique_mask],
                "y": y[unique_mask],
                "participation_id": participant_id,
            }
        )

    if not observers:
        raise ValueError(f"No valid gaze rows found in {csv_path}")

    return observers


def rel_yx_to_ij(y: float, x: float, height: int, width: int) -> tuple[int, int]:
    return int(y * (height - 1)), int(x * (width - 1))


def extract_fixation_coordinates(observer_fixations: dict[str, np.ndarray], height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    fix_y = observer_fixations["y"]
    fix_x = observer_fixations["x"]
    if len(fix_y) == 0:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    ij_list = [rel_yx_to_ij(y, x, height, width) for y, x in zip(fix_y, fix_x)]
    fix_i, fix_j = zip(*ij_list)
    return np.asarray(fix_i, dtype=np.int32), np.asarray(fix_j, dtype=np.int32)


def render_impulse_map(observers_gazes: list[dict[str, np.ndarray]], height: int, width: int, sigma: float) -> np.ndarray:
    sm = np.zeros((height, width), dtype=np.float32)
    num_observers = len(observers_gazes)
    base_weight = 2.0 * math.pi * sigma * sigma

    for observer_fixations in observers_gazes:
        fix_i, fix_j = extract_fixation_coordinates(observer_fixations, height, width)
        if len(fix_i) == 0:
            continue
        weight = base_weight / num_observers / len(fix_i)
        np.add.at(sm, (fix_i, fix_j), weight)

    return sm


class HeatmapGenerator:
    def __init__(
        self,
        observers_data: list[dict[str, np.ndarray | int]],
        height: int,
        width: int,
        fps: float,
        sigma_ref_px: float,
        extrapolate_empty_gazes: bool = True,
    ) -> None:
        if not observers_data:
            raise ValueError("observers_data is empty")

        self.observers_data = observers_data
        self.height = height
        self.width = width
        self.fps = fps
        self.spf = 1.0 / fps
        self.sigma = sigma_ref_px / 1920.0 * width
        self.extrapolate_empty_gazes = extrapolate_empty_gazes

    def _observer_gazes_in_range(
        self,
        observer_data: dict[str, np.ndarray | int],
        t_begin: float,
        t_end: float,
    ) -> dict[str, np.ndarray]:
        ts = observer_data["t"]
        index_begin = int(np.searchsorted(ts, t_begin, side="left"))
        index_end = int(np.searchsorted(ts, t_end, side="left"))

        if index_begin == index_end and self.extrapolate_empty_gazes:
            if index_begin > 0:
                index_begin -= 1
            else:
                return {
                    "x": np.asarray([0.5], dtype=np.float64),
                    "y": np.asarray([0.5], dtype=np.float64),
                    "t": np.asarray([t_begin], dtype=np.float64),
                }

        return {
            "x": observer_data["x"][index_begin:index_end],
            "y": observer_data["y"][index_begin:index_end],
            "t": observer_data["t"][index_begin:index_end],
        }

    def get_frame_impulse(self, frame_index: int) -> np.ndarray:
        t_begin = self.spf * frame_index
        t_end = self.spf * (frame_index + 1)
        observers_gazes = [
            self._observer_gazes_in_range(observer_data, t_begin, t_end)
            for observer_data in self.observers_data
        ]
        return render_impulse_map(observers_gazes, self.height, self.width, self.sigma)


def build_decoder(video_path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(video_path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-vsync",
            "0",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_encoder(
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    original_video_path: Path,
    keep_audio: bool,
) -> subprocess.Popen[bytes]:
    command = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:.8f}",
        "-i",
        "-",
    ]
    if keep_audio:
        command += [
            "-i",
            str(original_video_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0?",
            "-c:a",
            "copy",
            "-shortest",
        ]
    command += [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def normalize_map(sm_map: np.ndarray) -> np.ndarray:
    max_value = float(sm_map.max())
    if max_value <= 0.0:
        return np.zeros_like(sm_map, dtype=np.float32)
    sm_map = sm_map.astype(np.float32) / max_value
    return np.clip(sm_map, 0.0, 1.0)


def upscale_map(sm_map: np.ndarray, width: int, height: int) -> np.ndarray:
    image = Image.fromarray((sm_map * 255.0).astype(np.uint8), mode="L")
    image = image.resize((width, height), RESAMPLE_BILINEAR)
    return np.asarray(image, dtype=np.float32) / 255.0


def colorize_heatmap(heat: np.ndarray, max_opacity: float) -> tuple[np.ndarray, np.ndarray]:
    anchors = np.asarray(
        [
            [0.00, 0, 0, 0],
            [0.20, 100, 0, 0],
            [0.45, 220, 20, 0],
            [0.75, 255, 180, 0],
            [1.00, 255, 255, 210],
        ],
        dtype=np.float32,
    )

    flat = heat.reshape(-1)
    rgb = np.empty((flat.size, 3), dtype=np.float32)
    for channel in range(3):
        rgb[:, channel] = np.interp(flat, anchors[:, 0], anchors[:, channel + 1])
    rgb = rgb.reshape(heat.shape + (3,))

    alpha = np.clip((heat - 0.05) / 0.95, 0.0, 1.0) ** 0.8
    alpha *= max_opacity
    return rgb, alpha[..., None]


def overlay_heatmap(frame: np.ndarray, heat: np.ndarray, max_opacity: float) -> np.ndarray:
    rgb, alpha = colorize_heatmap(heat, max_opacity=max_opacity)
    frame_float = frame.astype(np.float32)
    blended = frame_float * (1.0 - alpha) + rgb * alpha
    return np.clip(blended, 0, 255).astype(np.uint8)


def render_heatmap_overlay(
    csv_path: Path,
    video_path: Path,
    output_path: Path,
    sigma_ref_px: float,
    map_width: int,
    map_height: int,
    max_opacity: float,
    participant_ids: set[int] | None,
    drop_audio: bool,
) -> dict[str, object]:
    meta = probe_video(video_path)
    observers = load_observers_data(csv_path, participant_ids=participant_ids)
    generator = HeatmapGenerator(
        observers_data=observers,
        height=map_height,
        width=map_width,
        fps=float(meta["fps"]),
        sigma_ref_px=sigma_ref_px,
        extrapolate_empty_gazes=True,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    decoder = build_decoder(video_path)
    encoder = build_encoder(
        output_path=output_path,
        width=int(meta["width"]),
        height=int(meta["height"]),
        fps=float(meta["fps"]),
        original_video_path=video_path,
        keep_audio=bool(meta["has_audio"]) and not drop_audio,
    )

    frame_size = int(meta["width"]) * int(meta["height"]) * 3
    frames_written = 0

    try:
        for frame_index in range(int(meta["frame_count"])):
            chunk = decoder.stdout.read(frame_size)
            if len(chunk) < frame_size:
                break

            frame = np.frombuffer(chunk, dtype=np.uint8).reshape((int(meta["height"]), int(meta["width"]), 3)).copy()
            sm_impulse = generator.get_frame_impulse(frame_index)
            sm_blurred = gaussian_filter(sm_impulse.astype(np.float32), sigma=generator.sigma, mode="constant")
            sm_norm = normalize_map(sm_blurred)
            sm_upscaled = upscale_map(sm_norm, int(meta["width"]), int(meta["height"]))
            frame_overlay = overlay_heatmap(frame, sm_upscaled, max_opacity=max_opacity)

            encoder.stdin.write(frame_overlay.tobytes())
            frames_written += 1

            if (frame_index + 1) % 50 == 0 or frame_index + 1 == int(meta["frame_count"]):
                print(f"Rendered {frame_index + 1}/{int(meta['frame_count'])} frames", flush=True)
    finally:
        if decoder.stdout:
            decoder.stdout.close()
        decoder_stderr = decoder.stderr.read().decode("utf-8", errors="replace") if decoder.stderr else ""
        decoder.wait()

        if encoder.stdin:
            encoder.stdin.close()
        encoder_stderr = encoder.stderr.read().decode("utf-8", errors="replace") if encoder.stderr else ""
        encoder.wait()

    if decoder.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed:\n{decoder_stderr.strip()}")
    if encoder.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed:\n{encoder_stderr.strip()}")
    if frames_written == 0:
        raise RuntimeError("No frames were written to the output video")

    return {
        "csv_path": str(csv_path),
        "video_path": str(video_path),
        "output_path": str(output_path),
        "participants": len(observers),
        "width": int(meta["width"]),
        "height": int(meta["height"]),
        "fps": float(meta["fps"]),
        "duration": float(meta["duration"]),
        "frame_count": frames_written,
        "internal_map_width": map_width,
        "internal_map_height": map_height,
        "sigma_px_internal": float(generator.sigma),
        "max_opacity": float(max_opacity),
    }


def main() -> None:
    args = parse_args()
    participant_ids = set(args.participant_ids) if args.participant_ids else None
    result = render_heatmap_overlay(
        csv_path=args.csv_path,
        video_path=args.video_path,
        output_path=args.output_path,
        sigma_ref_px=args.sigma_ref_px,
        map_width=args.map_width,
        map_height=args.map_height,
        max_opacity=args.max_opacity,
        participant_ids=participant_ids,
        drop_audio=args.drop_audio,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a heatmap overlay video into a palette-based GIF."
    )
    parser.add_argument("--input-video", type=Path, required=True)
    parser.add_argument(
        "--output-gif",
        type=Path,
        default=None,
        help="Optional output path. Default: replace .mp4 with .gif next to the video.",
    )
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument(
        "--dither",
        default="bayer",
        choices=["bayer", "sierra2_4a", "none"],
        help="GIF palette dithering mode.",
    )
    parser.add_argument(
        "--bayer-scale",
        type=int,
        default=5,
        help="Used only when --dither=bayer.",
    )
    return parser.parse_args()


def run_command(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Command failed")


def make_gif(
    input_video: Path,
    output_gif: Path,
    fps: int,
    width: int,
    dither: str,
    bayer_scale: int,
) -> Path:
    output_gif.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        palette_path = Path(tmp.name)

    try:
        run_command(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-i",
                str(input_video),
                "-vf",
                f"fps={fps},scale={width}:-1:flags=lanczos,palettegen=stats_mode=diff",
                str(palette_path),
            ]
        )

        if dither == "bayer":
            paletteuse = f"paletteuse=dither=bayer:bayer_scale={bayer_scale}:diff_mode=rectangle"
        elif dither == "none":
            paletteuse = "paletteuse=dither=none:diff_mode=rectangle"
        else:
            paletteuse = f"paletteuse=dither={dither}:diff_mode=rectangle"

        run_command(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-i",
                str(input_video),
                "-i",
                str(palette_path),
                "-lavfi",
                f"fps={fps},scale={width}:-1:flags=lanczos[x];[x][1:v]{paletteuse}",
                str(output_gif),
            ]
        )
    finally:
        palette_path.unlink(missing_ok=True)

    return output_gif


def main() -> None:
    args = parse_args()
    output_gif = args.output_gif or args.input_video.with_suffix(".gif")
    result = make_gif(
        input_video=args.input_video,
        output_gif=output_gif,
        fps=args.fps,
        width=args.width,
        dither=args.dither,
        bayer_scale=args.bayer_scale,
    )
    print(result)


if __name__ == "__main__":
    main()

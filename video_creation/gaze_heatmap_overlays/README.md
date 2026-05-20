# Gaze Heatmap Overlays

## Scripts

- [render_heatmap_overlay.py](./render_heatmap_overlay.py)
- [make_gif.py](./make_gif.py)

## What this subfolder is for

These scripts create qualitative video assets from raw gaze CSV files:

1. build an aggregate screen-space heatmap over the source video
2. render that heatmap as a semi-transparent color overlay on top of the frames
3. optionally convert the resulting MP4 into a lightweight GIF for quick sharing

This is useful when you want to inspect where participants looked over time without running the full mesh-space evaluation pipeline.

## Expected inputs

### Raw gaze CSV

The renderer expects a CSV in the same format as the model CSVs in `GAZE_DATA/csv_for_models/...`, with at least:

- `participation_id`
- `data_gazes`

`data_gazes` should be a Python-literal dictionary with:

- `t`: timestamps in seconds
- `x`: normalized horizontal coordinates in `[0, 1]`
- `y`: normalized vertical coordinates in `[0, 1]`

Each CSV row is treated as one observer.

### Video

The video can be any MP4 readable by `ffmpeg`. The script reads resolution, FPS, duration, and audio presence via `ffprobe`.

## What `render_heatmap_overlay.py` does

For each frame the script:

1. collects all gaze samples whose timestamps fall into that frame interval
2. deposits the samples into an internal screen-space impulse map
3. applies Gaussian blur to get a smooth heatmap
4. normalizes and colorizes the heatmap
5. overlays it on top of the original frame
6. writes an H.264 MP4, preserving the original audio track by default

Important behavior:

- by default all rows in the CSV are used
- each observer contributes equally inside a frame
- if a frame has no new sample for an observer, the previous sample is reused

## What `make_gif.py` does

This script converts an overlay MP4 into a palette-based GIF using a two-pass `ffmpeg` workflow:

1. generate an adaptive palette
2. render the GIF using that palette

This produces noticeably cleaner GIFs than a one-pass conversion.

## Dependencies

Python packages:

- `numpy`
- `pandas`
- `Pillow`
- `scipy`

System tools:

- `ffmpeg`
- `ffprobe`

## Main parameters

### `render_heatmap_overlay.py`

- `--csv-path`
  - raw gaze CSV
- `--video-path`
  - source video
- `--output-path`
  - destination overlay MP4
- `--sigma-ref-px`
  - reference blur sigma in 1920px-wide space, default: `40`
- `--map-width`
  - internal heatmap width before resize, default: `960`
- `--map-height`
  - internal heatmap height before resize, default: `540`
- `--max-opacity`
  - maximum overlay opacity, default: `0.82`
- `--participant-ids`
  - optional participant subset
- `--drop-audio`
  - disable audio copy into the output MP4

### `make_gif.py`

- `--input-video`
  - source overlay MP4
- `--output-gif`
  - destination GIF, optional
- `--fps`
  - output GIF FPS, default: `12`
- `--width`
  - output GIF width, default: `640`
- `--dither`
  - dithering mode, default: `bayer`

## Typical workflow

### 1. Render an overlay MP4

```bash
python3 video_creation/gaze_heatmap_overlays/render_heatmap_overlay.py \
  --csv-path /path/to/GAZE_DATA/csv_for_models/MeshMamba_non_texture/Aquarium_Deep_Sea_Diver_v1_L1.csv \
  --video-path /path/to/GAZE_DATA/videos/non_textured_videos/MeshMamba_non_texture_Aquarium_Deep_Sea_Diver_v1_L1.mp4 \
  --output-path results/video_creation/Aquarium_Deep_Sea_Diver_v1_L1_heatmap_overlay.mp4
```

### 2. Convert that MP4 into a GIF

```bash
python3 video_creation/gaze_heatmap_overlays/make_gif.py \
  --input-video results/video_creation/Aquarium_Deep_Sea_Diver_v1_L1_heatmap_overlay.mp4 \
  --output-gif results/video_creation/Aquarium_Deep_Sea_Diver_v1_L1_heatmap_overlay.gif
```

## Example: use only a subset of participants

```bash
python3 video_creation/gaze_heatmap_overlays/render_heatmap_overlay.py \
  --csv-path /path/to/model.csv \
  --video-path /path/to/model.mp4 \
  --output-path results/subset_overlay.mp4 \
  --participant-ids 26446 26936 29065
```

## Example: more compact GIF

```bash
python3 video_creation/gaze_heatmap_overlays/make_gif.py \
  --input-video results/subset_overlay.mp4 \
  --output-gif results/subset_overlay_small.gif \
  --fps 8 \
  --width 480
```

## Output behavior

The renderer prints a JSON summary at the end with:

- number of participants used
- source resolution and FPS
- duration and frame count
- internal heatmap size
- effective blur sigma in the internal map

## Limitations

- this is a screen-space qualitative visualization tool, not a mesh-space metric benchmark
- the heatmap is built from normalized 2D gaze points, not from projected mesh hits
- overlay colors and opacity are tuned for readability, not for quantitative interpretation

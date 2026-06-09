# Heatmap-on-Mesh Video Renderer

Renders per-frame heatmap-on-mesh videos using placement JSON object pose.
Each frame applies the project timing contract (1.8 s head / 0.2 s tail crop)
and the canonical blender_rig transform: recenter → scale → rotate_x(90°) →
rotate_z(per-frame).

## Files

| File | Purpose |
|------|---------|
| `render_heatmap_video.py` | Main CLI renderer |
| `run_server_heatmap_video_smoke.sh` | Smoke test (4 cases, 120 frames) on vg-iai |

## Usage

```bash
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset MeshMamba --track non_texture --model Starfruit_L3 \
  --map-type screen_space \
  --map-file /path/to/Starfruit_L3_screen_space_faces.txt \
  --mesh /path/to/Starfruit_L3.obj \
  --placement-json jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_Starfruit_L3.json \
  --output-dir /tmp/heatmap_videos \
  --fps 30 --alpha 0.8 --colormap jet --max-frames 120
```

## Key arguments

| Argument | Default | Notes |
|----------|---------|-------|
| `--map-type` | required | `screen_space`, `cone`, or `gt` |
| `--map-file` | required | Per-face or per-vertex `.txt` saliency file |
| `--alpha` | 1.0 | Heatmap opacity; blends with neutral gray |
| `--colormap` | `jet` | Any matplotlib colormap |
| `--max-frames` | all | Limit to first N frames (debug) |
| `--width/--height` | 960×540 | Output resolution |
| `--gt-column` | 7 | Column index for multi-column GT files (SAL3D) |
| `--keep-frames` | off | Retain individual PNGs after assembly |

## Map domain detection

Map length is compared to `n_faces` and `n_vertices` automatically:
- MeshMamba evaluators produce per-face files (`*_faces.txt`)
- SAL3D evaluators produce per-vertex files (`*_vertices.txt`)
- GT files use the same auto-detection

Multi-column files (SAL3D `Gaze/*.txt`) use `--gt-column 7` by default.

## Outputs

```
{output-dir}/{dataset}/{track}/{model}/{map-type}/
  heatmap_video.mp4
  manifest.json
```

`manifest.json` records all provenance: mesh, map, placement JSON path,
timing contract parameters, render resolution, map domain, and frame count.

## Dependencies

PyVista (off-screen rendering), Pillow (PNG I/O), matplotlib (colormap),
ffmpeg (video assembly). All present in the `reproject-benchmark` conda
environment on the server.

## Smoke test

Run 4 cases (120 frames each) on vg-iai:

```bash
cd /mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
bash video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh
```

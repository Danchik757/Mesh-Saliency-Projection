# Heatmap-on-Mesh Video Renderer

Renders per-frame heatmap-on-mesh videos from a saliency map and a placement JSON.
The mesh rotates one full turn per the rc3 timing contract; the heatmap is painted
onto mesh faces (or vertices) using a jet colormap on a white background.

## Files

| File | Purpose |
|------|---------|
| `render_heatmap_video.py` | Main CLI renderer |
| `run_server_heatmap_video_smoke.sh` | Smoke script (4 models, 120 frames) on vg-iai |

## Inputs

| Input | Source |
|-------|--------|
| Mesh OBJ | Dataset mesh file (MeshMamba, SAL3D, or 3DVA shared SAL3D mesh) |
| Placement JSON | `jsons/object_placement/{dataset}_jsons/{prefix}_{model}.json` |
| Saliency map | Per-face or per-vertex `.txt` file (GT, cone, or screen_space) |

## Supported map types (`--map-type`)

| Value | Source convention |
|-------|-------------------|
| `gt` | Ground-truth fixation-derived per-face file |
| `cone` | Cone-projection prediction map (`*_cone_faces.txt` or `*_cone_vertices.txt`) |
| `screen_space` | Screen-space Gaussian prediction map |

Map domain (face vs. vertex) is **auto-detected** by comparing map length to
`n_faces` and `n_vertices`. Mismatch raises a hard error. Multi-column GT files
(SAL3D `Gaze/*.txt`) select column via `--gt-column` (default 7).

**Map provenance rule:** GT smoke uses `sal3d_fixed_face_gt/` or MeshMamba per-face
CSVs. Prediction maps for rc3 visualization **must** come from `rc3_full_metrics`
outputs — never from old `sal3d_pilot_test` / `meshmamba_geodesic_test` folders.

## Per-dataset transform convention

The OBJ vertex pipeline must match the Blender render script that produced
the participant videos. The key difference is how each dataset's OBJ was imported:

| Dataset | Blender OBJ import | `extra_rotate_x_deg` |
|---------|-------------------|---------------------|
| 3DVA | `up_axis='Z'` (OBJ already Z-up) | **0°** |
| SAL3D | default Y-up → Blender rotX(90°) | **90°** |
| MeshMamba | default Y-up → Blender rotX(90°) | **90°** |

The renderer auto-selects from `_DATASET_EXTRA_ROTATE_X`; override with
`--extra-rotate-x-deg` if needed. Using the wrong value produces a rotated/tilted
view that does not match the participant video.

Full transform order (matches evaluator `blender_rig` canonical):
```
recenter → scale → rotX(extra_rotate_x_deg) → rotZ(per-frame) → +location
```

## Key CLI arguments

| Argument | Default | Notes |
|----------|---------|-------|
| `--map-type` | required | `gt`, `cone`, or `screen_space` |
| `--map-path` | required | Per-face or per-vertex saliency `.txt` |
| `--background-color` | `white` | PyVista background (default white) |
| `--full-turn` | off | Render complete turn: 450 f (3DVA/MM), 660 f (SAL3D). Implies `--allow-full-batch`. |
| `--max-frames` | all / smoke cap | Cap to N frames; combined with `--full-turn` as upper bound |
| `--extra-rotate-x-deg` | auto (per dataset) | Override per-dataset X rotation |
| `--alpha` | 1.0 | Heatmap opacity; blends with neutral gray |
| `--colormap` | `jet` | Any matplotlib colormap |
| `--width / --height` | 960×540 | Output resolution |
| `--gt-column` | 7 | Column index for multi-column GT files |
| `--keep-frames` | off | Retain individual PNGs after video assembly |
| `--allow-full-batch` | off | Bypass smoke frame cap (120 GPU / 30 CPU) |
| `--skip-gpu-preflight` | off | Skip GPU probe (tests only) |

## GPU preflight

Before any long render, the renderer probes the GPU backend via PyVista/VTK
and sets WSL D3D12 env vars (`GALLIUM_DRIVER=d3d12`,
`MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA`) to route Mesa to the physical GPU.
On RTX 2060 via WSL D3D12 bridge: ~0.05 s/frame, 450 frames ≈ 23 s.

The manifest records `gpu_preflight.gpu_available`, `used_cpu_fallback`, and
`opengl_renderer`. If CPU fallback (llvmpipe/softpipe) is detected, frame count
is capped at 30 without `--allow-full-batch`.

## GT smoke status

GT-only smoke has run and produced correct output for:
- MeshMamba non_texture: Starfruit_L3, Watermelon_V1_L3, Statue_v1_L2_David, barbiegirl_V1_L3
- MeshMamba rgb_texture: Kangaroo_v1_L3, Military_Action_Figure_SG_v2_L3, Apple_Red_v1_L3
- SAL3D: alien2, james, torso, vase
- 3DVA: camel, michael3, torso (using SAL3D GT maps on corrected 0° X rotation)

Prediction smoke (cone / screen_space) requires rc3_full_metrics map outputs
from the server (blocked locally).

## Outputs per model

```
{output-dir}/{dataset}/{track}/{model}/{map-type}/
  heatmap_video.mp4
  manifest.json          # full provenance: mesh, map, timing, GPU, transform
  manifest.csv           # same fields flattened for spreadsheet
  preview_frame_*.png    # 5 preview frames at 0%, 25%, 50%, 75%, 100%
```

`manifest.json` records: `dataset`, `model`, `map_type`, `map_file`, `mesh_file`,
`placement_json`, `timing_contract` (name, frame_offset, start/end, fps,
dataset_turn_frames), `render` (n_rendered_frames, fps, width, height, colormap,
background_color, extra_rotate_x_deg, map_domain, n_map_elements, n_mesh_vertices,
n_mesh_faces, input_min, input_max, display_normalization), `gpu_preflight`.

## Example commands

```bash
# MeshMamba GT full-turn (white bg)
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Starfruit_L3 \
  --map-type gt \
  --map-path /path/to/MeshMamba/dataset/SaliencyMap/non_texture/Starfruit-L3.csv \
  --mesh /path/to/MeshMamba/dataset/MeshFile/non_texture/Starfruit_L3/Starfruit-L3.obj \
  --output-dir /tmp/heatmap_out \
  --background-color white --full-turn

# 3DVA GT smoke (120 frames, corrected 0° X rotation applied automatically)
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset 3dva --model camel \
  --map-type gt \
  --map-path /path/to/sal3d_benchmark_pkg/sal3d_fixed_face_gt/camel_faces.txt \
  --mesh /path/to/sal3d_benchmark_pkg/Meshes/camel.obj \
  --output-dir /tmp/heatmap_out \
  --background-color white --max-frames 120

# Cone map smoke (rc3_full_metrics required on server)
python video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Starfruit_L3 \
  --map-type cone \
  --map-path /path/to/rc3_full_metrics/Starfruit_L3_cone_faces.txt \
  --mesh /path/to/Starfruit-L3.obj \
  --output-dir /tmp/heatmap_out \
  --background-color white --max-frames 120
```

## Known limitations

- Prediction maps (cone, screen_space) require `rc3_full_metrics` server outputs
  not available locally.
- 3DVA combined GT requires `build_3dva_combined_gt.py` (raw fixation data on server).
  Current 3DVA renders use SAL3D fixed-face GT (same geometry, different experiment).
- Full batch across all models must not be launched without reviewer/controller approval.
- `--full-turn` renders the first N frames (from offset 0); no mid-sequence crop.

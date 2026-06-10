# Windows Claude Task: Heatmap-on-Mesh Video Renderer

## Role and Constraints

You are `claude_windows`, working from WSL on your own repository clone.

Do not launch server metric jobs.

Do not change metric evaluator logic for `screen_space_gaussian` or `cone_gaussian_on_mesh`.

Commits must be authored as the human project owner. Do not mention Claude, AI, or yourself as a contributor in commit messages, code comments, README text, or generated metadata.

Append progress and decisions to:

```text
coordination/agents/WINDOWS_CLAUDE.md
```

## Goal

Implement a video renderer that overlays a saliency/heatmap directly on the rendered object surface and produces an output video using our method outputs and/or GT maps.

This is different from the six-view static heatmap task assigned to macOS Claude.

Your task is video-oriented:

1. Use the same object placement / rotation JSON that was used for the original rendered videos.
2. Render the object frame-by-frame in the correct pose over time.
3. Color the mesh surface with a heatmap.
4. Export a video showing the object with the heatmap on it.

## Target Datasets

Prioritize:

```text
MeshMamba non_texture
MeshMamba rgb_texture
SAL3D
```

3DVA can be left for later unless the reviewer explicitly assigns it.

## Heatmap Sources

Support these map types:

```text
screen_space_gaussian prediction
cone_gaussian_on_mesh prediction
GT
```

Use existing metric run outputs where possible:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/full_20260609
```

For local development, you may use smoke outputs:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/smoke_parallel_20260609
```

MeshMamba maps are per-face.

SAL3D maps may be per-vertex or per-face depending on the evaluator output; detect map length and fail clearly on mismatch.

## Rendering Contract

The output video must use the object pose/rotation from placement JSON. Do not make a static turntable unless the placement JSON is unavailable.

The timing contract is the project timing contract:

```text
crop first 1.8 seconds
crop last 0.2 seconds
use the remaining one full object turn
derive frame count / rotation speed from placement JSON
```

Do not use legacy CSV timestamps for video timing.

## Visual Requirements

Use `jet` colormap for heatmap colors.

Render heatmap directly on the object surface.

The base object may be neutral gray with heatmap color overlay, or textured with heatmap blended on top if texture support is reliable.

Implement at least:

```text
--map-type screen_space|cone|gt
--alpha
--colormap jet
--fps
--max-frames for quick debug
```

Output should include:

```text
<dataset>/<track>/<model>/<map_type>/heatmap_video.mp4
<dataset>/<track>/<model>/<map_type>/manifest.json
```

## Implementation Location

Create:

```text
video_creation/heatmap_on_mesh_video/
```

Suggested files:

```text
video_creation/heatmap_on_mesh_video/render_heatmap_video.py
video_creation/heatmap_on_mesh_video/README.md
video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh
```

Do not store generated videos in git.

## Server

Final smoke rendering should run on:

```text
ssh vg-iai
```

Server root:

```text
/mnt/ssd1/29d_kon/acm_2026
```

Use low priority:

```bash
nice -n 15
ionice -c2 -n7
```

Use environment:

```bash
cd /mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
export REPROJECT_SERVER_ROOT=/mnt/ssd1/29d_kon/acm_2026
export REPROJECT_WORKSPACE_NAME=coordinator
export CONDA_ENV_NAME=reproject-benchmark
source configs/server_vg_intellect.env
```

## Smoke Scope

Do not render every model at first.

Start with:

```text
MeshMamba non_texture Starfruit_L3 screen_space
MeshMamba non_texture Starfruit_L3 cone
SAL3D bunny screen_space
SAL3D bunny cone
```

Use `--max-frames 120` for first smoke.

After reviewer approval, extend to full videos.

## Validation

Before reporting completion:

```bash
python -m py_compile video_creation/heatmap_on_mesh_video/render_heatmap_video.py
python -m pytest -q
```

For server smoke, report:

```text
server output root
mp4 paths
manifest paths
frame count
map type
dataset/model
whether placement JSON timing was used
any rendering backend limitations
```


# macOS Claude Task: Six-View Jet Heatmaps for Non-3DVA Datasets

## Role and Constraints

You are `claude_macos`. Work in the local macOS repository clone.

Do not change metric evaluator logic unless the reviewer explicitly asks for it. This task is visualization-only.

Do not launch metric full runs. The reviewer/controller already launched metric jobs on `vg-iai`.

Commits must be authored as the human project owner. Do not mention Claude, AI, or yourself as a contributor in commit messages, code comments, README text, or generated metadata.

Append progress and decisions to:

```text
coordination/agents/MACOS_CLAUDE.md
```

## Goal

Implement and run a renderer that produces normal diagnostic heatmaps with the `jet` colormap directly on the object surface, viewed from 6 canonical directions, for every selected object.

Datasets:

```text
MeshMamba non_texture
MeshMamba rgb_texture
SAL3D
```

Do not include 3DVA in this task.

For each selected object, render three map types:

```text
screen_space_gaussian prediction
cone_gaussian_on_mesh prediction
GT saliency/fixation map
```

For each map type, render six object views:

```text
front
back
left
right
top
bottom
```

The bottom view is important because the user wants to check whether fixations/saliency appear on the lower side of objects.

## Server

Run final rendering on:

```text
ssh vg-iai
```

Server root:

```text
/mnt/ssd1/29d_kon/acm_2026
```

Coordinator repo on server:

```text
/mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
```

Use the already prepared environment:

```text
/mnt/ssd1/29d_kon/acm_2026/environments/reproject-benchmark/bin/python
```

Always run with low priority:

```bash
nice -n 15
ionice -c2 -n7
```

Also set:

```bash
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
```

## Data Roots

On `vg-iai`, source environment by using:

```bash
cd /mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection
export REPROJECT_SERVER_ROOT=/mnt/ssd1/29d_kon/acm_2026
export REPROJECT_WORKSPACE_NAME=coordinator
export CONDA_ENV_NAME=reproject-benchmark
source configs/server_vg_intellect.env
```

The env file name is legacy. The paths are correct for `vg-iai` because they are rooted at `/mnt/ssd1/29d_kon/acm_2026`.

Important roots after sourcing:

```text
$RELEASE_DATA_ROOT
$REPROJECT_PROCESSED_FIXATIONS_ROOT
$MESHMAMBA_NON_TEXTURE_ROOT
$MESHMAMBA_RGB_TEXTURE_ROOT
$SAL3D_DATASET_ROOT
$MESHMAMBA_JSON_ROOT
$MESHMAMBA_RGB_TEXTURE_JSON_ROOT
$SAL3D_JSON_ROOT
$OUTPUT_ROOT
```

The current metric full run writes to:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/full_20260609
```

The completed smoke outputs are:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/smoke_parallel_20260609/MeshMamba
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/smoke_parallel_20260609/SAL3D
```

Use smoke outputs for quick local/server debugging if the full run is not complete yet. For the final 10-object render batch, prefer `full_20260609` outputs.

## Required Output Layout

Write final rendered images to:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/heatmaps_6view_20260609
```

Use this structure:

```text
heatmaps_6view_20260609/
  MeshMamba/
    non_texture/
      <model>/
        screen_space/
          front.png
          back.png
          left.png
          right.png
          top.png
          bottom.png
          montage.png
        cone/
          ...
        gt/
          ...
    rgb_texture/
      <model>/
        ...
  SAL3D/
    <model>/
      screen_space/
      cone/
      gt/
  manifest.json
  summary.csv
  heatmaps_6view_20260609.tar.gz
```

`montage.png` should be a 2x3 grid containing the six views with labels.

`manifest.json` must include:

```text
dataset
texture_type when applicable
model
map_type: screen_space | cone | gt
mesh_path
map_path
gt_path when applicable
normalization mode
colormap: jet
rendered image paths
commit hash
server hostname
created_at
```

`summary.csv` must include one row per dataset/track/model/map_type and columns:

```text
dataset,texture_type,model,map_type,status,error_message,mesh_path,map_path,front,back,left,right,top,bottom,montage
```

## Object Selection

Render 10 models per dataset/track:

```text
MeshMamba non_texture: 10 models
MeshMamba rgb_texture: 10 models
SAL3D: 10 models
```

Selection rules:

1. Prefer models that have successful full-run reports for both `screen_space` and `cone`.
2. If full run is not complete, use smoke outputs only for implementation debugging, not as final 10-object delivery.
3. Skip known invalid/missing fixation cases.
4. Do not include 3DVA.
5. Keep the selected model list deterministic and write it to `manifest.json`.

If you need an initial deterministic list before full results complete, use the first 10 `ok` models sorted by model name from the long CSV for each dataset/track.

## Map Sources

MeshMamba prediction maps are per-face:

```text
screen_space: *_screen_space_faces.txt
cone:         *_cone_faces.txt or report-specific generated face map
GT:           SaliencyMap/<texture_type> CSV, one value per face
```

SAL3D prediction/GT maps may be per-vertex or per-face depending on the evaluator output. Detect the map length:

```text
if len(map) == len(mesh.vertices): color vertices
if len(map) == len(mesh.faces): color faces
otherwise fail that row and write the mismatch in summary.csv
```

Do not silently resample unless you explicitly document the rule. For this visualization task, exact length matching is preferred.

## Rendering Requirements

Use a deterministic offscreen renderer. Acceptable options:

```text
trimesh scene render if available
pyrender/osmesa if already available or easy to install
matplotlib 3D fallback if trimesh rendering is unavailable
Blender only if available and faster to make reliable
```

Do not require sudo.

Apply the heatmap directly to the mesh surface. Do not render a 2D heatmap next to the object only.

Use `jet` colormap.

Normalize colors per model and map type by default:

```text
minmax over positive + zero values in the rendered map
NaN/Inf -> 0
constant maps -> all cold/blue with a warning
```

Also implement a `--global-scale-per-model` option if simple: for a given model, compute one min/max across `screen_space`, `cone`, and `gt`, then render all three with the same color scale. If time is short, implement per-map minmax first and document that global scaling is TODO.

The object should be centered and scaled consistently across six views. The six-view renderer does not need to match the original video camera; it is a canonical diagnostic view of the saliency distribution.

Suggested canonical directions:

```text
front:  +Z looking toward origin
back:   -Z
left:   -X
right:  +X
top:    +Y
bottom: -Y
```

If the mesh coordinate convention makes top/bottom ambiguous for a dataset, document the chosen convention in `summary.csv` or `manifest.json`.

## Implementation Location

Create a new folder:

```text
visualization/heatmap_six_view/
```

Suggested files:

```text
visualization/heatmap_six_view/render_six_view_heatmaps.py
visualization/heatmap_six_view/README.md
visualization/heatmap_six_view/select_models_from_metric_csv.py
```

Do not place generated PNGs in git.

## CLI Requirements

The main renderer should support:

```bash
python visualization/heatmap_six_view/render_six_view_heatmaps.py \
  --dataset meshmamba \
  --texture-type non_texture \
  --metrics-root /mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/full_20260609/MeshMamba \
  --dataset-root "$MESHMAMBA_NON_TEXTURE_ROOT" \
  --json-root "$MESHMAMBA_JSON_ROOT" \
  --output-root /mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/heatmaps_6view_20260609 \
  --limit 10 \
  --map-types screen_space cone gt \
  --colormap jet
```

Equivalent command must work for:

```text
MeshMamba rgb_texture
SAL3D
```

## Run on vg-iai

After implementation and local syntax checks, run on `vg-iai` inside tmux:

```bash
tmux new-session -d -s heatmaps_6view_20260609 \
  "bash /mnt/ssd1/29d_kon/acm_2026/run_heatmaps_6view_20260609.sh"
```

The run script should:

1. Pull `reproject-benchmark`.
2. Source `configs/server_vg_intellect.env`.
3. Run the renderer for MeshMamba non_texture, MeshMamba rgb_texture, and SAL3D.
4. Create `heatmaps_6view_20260609.tar.gz`.
5. Print final download path:

```text
/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/heatmaps_6view_20260609/heatmaps_6view_20260609.tar.gz
```

## Validation

Before final server run:

```bash
python -m py_compile visualization/heatmap_six_view/render_six_view_heatmaps.py
python -m pytest -q
```

After rendering:

1. At least 30 models total: 10 MeshMamba non_texture, 10 MeshMamba rgb_texture, 10 SAL3D.
2. For each model: 3 map types x 6 views = 18 PNGs plus 3 montages.
3. `summary.csv` has no silent failures.
4. Open/check a few montages manually:
   - MeshMamba non_texture one model
   - MeshMamba rgb_texture one model
   - SAL3D one model
5. Confirm bottom view exists and is labeled.

## Report Back to Reviewer

When done, report:

```text
commit hash
server tmux session name
output root
tar.gz path
selected model lists
count of PNGs and montages
any failed models/map types and why
```


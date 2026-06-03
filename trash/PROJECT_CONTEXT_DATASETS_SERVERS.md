# Project Context, Datasets, Servers

Last updated: 2026-06-03 MSK.

This file is the first handoff document for a new agent. It summarizes what
the project is, where everything lives, which assumptions are authoritative,
and what must not be changed silently.

Read order for a new agent:

1. `trash/PROJECT_CONTEXT_DATASETS_SERVERS.md`
2. `trash/DATASET_STRUCTURE_AUDIT.md`
3. `trash/BENCHMARK_PIPELINES_COMMANDS.md`
4. `trash/RESULTS_ISSUES_NEXT_STEPS.md`
5. `trash/GPT.md`
6. `trash/Claude.md`

The original running logs are still `trash/GPT.md` and `trash/Claude.md`.
These handoff files are a curated, shorter, operational version of those logs.

## 1. Goal

We are building a reproducible benchmark pipeline for projecting gaze points
from video/screen coordinates onto 3D meshes and comparing the resulting
saliency maps with dataset ground truth.

Core task:

- Input: gaze CSV from participants, camera/object JSON from rendering.
- Projection: map 2D gaze points from video/screen to 3D mesh.
- Output: vertex-level or face-level predicted saliency map.
- Evaluation: compare prediction with GT fixation/saliency maps using metrics.

The project is not only "run metrics". A large part of the work is making sure
the object is placed in exactly the same camera view as in the original videos.
Incorrect camera/object alignment makes all projection metrics invalid.

## 2. Local Repository

Local repo:

```text
/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection
```

Current branch:

```text
reproject-benchmark
```

Recent committed HEAD observed on 2026-06-03:

```text
c1dca6c Append session 17 log to Claude.md: 3DVA GT analysis + eval fixes
```

Important: the working tree is not clean. There are uncommitted local changes
and untracked result folders/scripts. Do not run destructive git commands.

Observed dirty/untracked classes:

- Modified docs and preview tools:
  - `README.md`
  - `test/README.md`
  - `test/kld_parameter_sweep/README.md`
  - `test/tools/README.md`
  - `test/tools/preview_screenspace_alignment.py`
  - `trash/GPT.md`
- Untracked or newly generated code:
  - `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_geodesic.py`
  - `reprojection_methods/cone_projection_on_mesh/eval_sal3d_geodesic.py`
  - `test/kld_parameter_sweep/run_kld_postprocess_diagnostics.py`
  - `test/kld_parameter_sweep/server/run_diagnostic_vg_intellect.sh`
  - `test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh`
  - `test/tools/preview_meshmamba_cone_alignment.py`
  - `test/tools/preview_sal3d_screenspace_alignment.py`
  - `test/gt_visualizations/*`
- Untracked result archives:
  - `results/benchmark_runs/sal3d/`
  - `results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/`
  - `results/benchmark_runs/kld_diagnostic/`
  - `results/benchmark_runs/kld_postprocess/`
  - `results/diagnostics/`
  - `results/meshmamba_geodesic_test/`
  - `results/sal3d_geodesic_test/`

Do not assume a file is safe to delete just because it is untracked.

## 3. Server Profile

Primary server:

```text
ssh vg-intellect
```

Server constraints:

- No `sudo`.
- Use user-writable paths only.
- Use `tmux` for long jobs.
- Use low priority:

```bash
nice -n 10 ...
nice -n 15 ...
```

Server CPU profile mentioned by user:

- 64 CPUs
- AMD EPYC 7532 32-Core Processor

Server project root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING
```

Server repo path:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
```

Server output root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs
```

Server side-input root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs
```

Server environments root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/environments
```

Main Python environment:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark/bin/python
```

Server dataset root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets
```

Known dataset folders on server:

```text
3DVA
Huawei
MeshMambaSaliency
SAL3D
reproject_release_v1
```

Authoritative server env file in repo:

```text
configs/server_vg_intellect.env
```

Use it before server runs:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
source configs/server_vg_intellect.env
```

Important env values from that file:

```bash
export REPO_ROOT="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection"
export OUTPUT_ROOT="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs"
export SIDE_INPUTS_ROOT="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs"
export CONDA_ENVS_ROOT="/home/29d_kon@lab.graphicon.ru/ssd1_link/environments"
export CONDA_ENV_NAME="reproject-benchmark"
export REPROJECT_PYTHON="${CONDA_ENVS_ROOT}/${CONDA_ENV_NAME}/bin/python"
export WORKERS=12
export NICE_LEVEL=10
```

Important: earlier notes sometimes mention `vg-iai`. Current server for this
project is `vg-intellect`.

## 4. Local Data Roots

Common local roots used in this project:

```text
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA
/Users/admin/Documents/LAB/Dataset/3DVA
/Users/admin/Downloads/Telegram Desktop/rgb_textured_videos
/Users/admin/Downloads/Telegram Desktop/non_textured_videos
/Users/admin/Downloads/Telegram Desktop/3dva_videos 4
```

Important local gaze/result sources:

```text
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_datasets/results_SAL3D.csv
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/3DVA_json
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models
```

The local and server layouts are not identical. Do not hard-code local absolute
paths in server scripts. Use env vars.

## 5. Side Inputs

The datasets contain meshes/GT, but our projection also needs:

- participant gaze CSVs
- camera/object JSONs from rendering
- sometimes videos for preview overlay

Server-side expected side-input layout:

```text
${SIDE_INPUTS_ROOT}/3DVA/csv
${SIDE_INPUTS_ROOT}/3DVA/json
${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/csv
${SIDE_INPUTS_ROOT}/MeshMamba_non_texture/json
${SIDE_INPUTS_ROOT}/MeshMamba_rgb_texture/csv
${SIDE_INPUTS_ROOT}/MeshMamba_rgb_texture/json
${SIDE_INPUTS_ROOT}/SAL3D/csv
${SIDE_INPUTS_ROOT}/SAL3D/json
```

Known transferred logical counts from server setup, excluding macOS `._*`
AppleDouble files:

- 3DVA: 32 CSV + 32 JSON
- MeshMamba non_texture: 105 CSV + 105 JSON
- MeshMamba rgb_texture: 105 CSV + 105 JSON
- SAL3D release-root run used data under `reproject_release_v1`, not only
  `side_inputs`

Detailed verified counts and caveats are in:

```text
trash/DATASET_STRUCTURE_AUDIT.md
```

Transfer method:

- Prefer commit/pull for code.
- Use `scp` or tar + `scp` for side inputs and large data not committed to git.
- Do not let the secondary agent transfer files to the server without explicit
  project-owner/GPT approval.

## 6. Dataset Meaning and GT Granularity

### MeshMamba

Status: benchmark-ready as secondary track.

Tracks:

- `non_texture`
- `rgb_texture`

GT:

- per-face CSV
- under dataset:

```text
MeshMambaSaliency/SaliencyMap/non_texture/*.csv
MeshMambaSaliency/SaliencyMap/rgb_texture/*.csv
```

Meshes:

```text
MeshMambaSaliency/MeshFile/non_texture/<model>/<model>.obj
MeshMambaSaliency/MeshFile/rgb_texture/<model>/<model>.obj
```

Current canonical projection recipe:

- recenter object to bbox center
- `extra_rotate_x_deg=90`
- `projection_fov_mode=horizontal_to_vertical`
- `transform_order=blender_rig`
- JSON camera/object metadata is required

Important: high object/video mask IoU does not guarantee high GT metric
correlation. MeshMamba GT distribution often remains sparse/localized while our
prediction can be broad.

### SAL3D

Status: primary benchmark track for our video-like task, with caveats.

Why primary:

- Same general condition class: rotating object/video gaze.
- Our CSV/JSON correspond to the rendered video setup.

GT:

- official `Gaze/*.txt`
- operative GT column used in current scripts is column 6
- `Smooth_Gaze` is used when available to smooth/project GT to mesh vertices

Server run used release root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/jsons_for_models/SAL3D_json
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Smooth_Gaze
```

Known failures in full run:

- `MaxPlanck`
- `meca`
- `sofa`

Reason:

- GT rows: 20000
- OBJ vertex count mismatch for these models

Do not mix raw GT and smoothed GT rows in a final table without labeling it.

### 3DVA

Status: not primary GT for our dynamic-video task. Use as weak cross-condition
reference only.

GT:

- per-vertex TXT in `FixationMaps`
- each model has three views: `300`, `413`, `599`
- these are static viewpoints, not dynamic rotating video GT

Important conclusion from Claude session 17:

- 3DVA GT files correspond to three different static views.
- Dynamic rotating video fixations are significantly different from these static
  GT maps.
- 3DVA should not be used to claim our projection method is valid.

Use cases that are valid:

- external cross-condition reference
- comparison with published algorithms on the same GT
- sanity check for geometrically interesting regions

Use cases that are invalid:

- treating low CC vs 3DVA as a projection failure
- comparing our dynamic-video result to 3DVA human upper bound directly

Current rule:

- Always use `3DModels-Simplif-up`, not `3DModels-Simplif`.
- For 3DVA screen-space, use `sigma_px=49.0`.
- Prefer visible-only metrics if comparing against 3DVA GT.

Reference doc:

```text
datasets/3DVA_DATASET.md
```

## 7. Methods and Output Granularity

Main methods:

| Method | Main script family | Output | Main compatible datasets |
|---|---|---:|---|
| `screen_space_gaussian` | `reprojection_methods/screen_space_gaussian/*` | face or vertex | MeshMamba, SAL3D, 3DVA |
| `cone_gaussian_on_mesh` | `reprojection_methods/cone_projection_on_mesh/*` | face or vertex | MeshMamba, SAL3D, 3DVA |
| `raycast_nearest_vertex` | `eval_3dva_raycast_cone.py` | vertex | 3DVA |
| `raycast_nearest_face` | `eval_meshmamba_cone.py` | face | MeshMamba |
| `our_pipeline` | external `MAMBA_GAZE` | face | MeshMamba |
| `diffusion` / `geodesic` | new diagnostic/geodesic scripts | face or vertex | MeshMamba, SAL3D |

Granularity rules:

- MeshMamba GT is per-face. Use face-level prediction.
- SAL3D current GT comparison is per-vertex.
- 3DVA GT is per-vertex.
- If converting vertex to face or face to vertex, explicitly label it as an
  adaptation. Do not present it as identical to a native method.

## 8. Preview and Alignment Philosophy

Alignment must be validated visually before trusting metrics.

Preview sources:

- Fast Python/trimesh previews are useful for iteration.
- Blender canonical previews are the source of truth when exact video matching
  matters.

Canonical Blender path:

```text
test/blender_canonical/render_preview_from_manifest_blender.py
test/blender_canonical/evaluate_blender_mask_batch.py
```

Why Blender:

- original videos were rendered in Blender
- Blender import/origin/camera behavior can differ from local Python rasterizer
- if Blender preview does not match video, the remaining mismatch is not from
  the local rasterizer

Representative preview/visualization folders:

```text
test/manifests/
test/output_local/preview_checks/
test/output_local/blender_mask_batch_*
test/gt_visualizations/
test/output_local/meshmamba_bad_kld/
results/diagnostics/2026-06-02_meshmamba_worst_cases/
```

## 9. Collaboration Protocol

There were two agents:

- GPT: main project orchestration, final user-facing decisions, server launch.
- Claude: delegated audits, fixes, extra implementations, append-only notes.

Protocol for future agents:

1. Read these handoff docs first.
2. Read `trash/GPT.md` and `trash/Claude.md` for historical detail.
3. Inspect `git status --short`.
4. Do not assume untracked files are disposable.
5. Do not run server jobs, `scp`, or `git push` without explicit approval.
6. Append major decisions to `trash/GPT.md` or a new dated handoff note.
7. Keep datasets separate. Do not average MeshMamba, SAL3D, and 3DVA together.

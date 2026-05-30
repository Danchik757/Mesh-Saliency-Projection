# Handoff For Next Agent

Last updated: 2026-05-30 MSK

## Goal

Continue the project from the current state without losing context.

Main project goal:

1. Validate correct object placement/projection from gaze data onto meshes.
2. Use `json` camera/object metadata as the source of truth.
3. Compare methods and metrics across datasets.
4. Prepare a reproducible server workflow on `vg-intellect`.

This file is intentionally detailed because the previous agent is at context
limit and cannot continue safely.

## Operational Safety Rules

Read this before doing anything practical.

This project currently has three separate tracks that must not be mixed
carelessly:

1. preview/image validation
2. server transfer/setup
3. metric computation

Correct execution order:

1. verify repo state
2. verify server repo state
3. verify server environment state
4. verify side-input transfer state
5. verify preview/image alignment state
6. launch only pilot metric runs
7. only after pilot success launch broader runs

Common failure modes to avoid:

1. changing geometry recipe and comparing new metrics against old runs as if
   they used the same transform
2. treating one model-specific correction as a dataset-wide constant
3. skipping `json` and hardcoding camera/object placement by hand
4. starting full benchmark before representative preview validation
5. assuming server setup completed if a previous remote command was interrupted

## Absolute Paths

Main repo:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection`

External local MeshMamba repo:

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE`

Local dataset roots:

`/Users/admin/Documents/LAB/Dataset/3DVA`

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency`

Local gaze side-input roots:

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA`

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/3DVA_json`

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_non_texture`

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/Mamba_non_textured`

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_rgb_texture`

`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/Mamba_rgb_textured`

Local original video folders used for visual validation:

`/Users/admin/Downloads/Telegram Desktop/3dva_videos 4`

`/Users/admin/Downloads/Telegram Desktop/non_textured_videos`

`/Users/admin/Downloads/Telegram Desktop/rgb_textured_videos`

## Current Git State

Working branch:

`reproject-benchmark`

Last known verified commits:

1. `85c187e` `Add preview calibration and server pilot wrappers`
2. `cc7cffb` `append Claude.md log for fixes A-C (wrappers, side-inputs, path audit)`
3. `9a55147` `Refine MeshMamba pilot and scp dry-run`

Remote state:

`origin/reproject-benchmark` exists and points to `9a55147`

Important:

At the moment of handoff, local repo was clean except for:

`trash/Claude.md`

Do not overwrite user/other-agent changes there. Read first.

## What Was Achieved For Correct Object Display

### Key Rule

`json` is the base truth for:

1. `camera_static.view_matrix`
2. `camera_static.projection_matrix`
3. `camera_static.fov_degrees`
4. `model_static.scale`
5. `model_static.location`
6. `frames[i].rotation_z_*`

Only corrective overrides are allowed on top:

1. `recenter_to_bbox_center`
2. `extra_rotate_x_deg`
3. `override_fov_deg`

### What "Correct Display" Means Here

The preview task is not about photorealism. It is about geometric consistency
between:

1. original video frame
2. rendered preview from `OBJ + JSON`
3. later screen-to-mesh projection of gaze points

A preview is considered "good enough" when:

1. the object is in approximately the same place in the frame
2. the silhouette/orientation is approximately the same
3. the object occupies approximately the same image scale
4. there is no obvious pivot/origin mismatch

For `MeshMamba rgb_texture`, geometry-only preview was accepted by the user for
this phase because the goal is pose/framing validation, not texture fidelity.

### Implemented Portable Preview Flow

Main portable renderer inside repo:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/tools/render_preview_from_manifest.py`

Wrapper scripts:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_preview_manifest.sh`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_preview_suite.sh`

Env examples:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/env/local_paths.example.sh`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/env/vg_intellect_paths.example.sh`

Important implementation facts:

1. the renderer supports env-expanded manifest paths
2. if `video_path` exists in the manifest, the tool extracts a real frame from
   the source video
3. then it produces a side-by-side `video frame vs rendered preview` image
4. this side-by-side compare is the exact method previously used to decide
   whether orientation/FOV/recenter corrections were needed

### Validated Preview Results

### Status Of The Image-Validation Task

This task is not globally finished, but it is also not untouched.

What is already done:

1. the compare workflow exists and works
2. representative compare checks were completed for:
   - `3DVA bunny`
   - `MeshMamba non_texture Starfruit_L3`
   - `MeshMamba rgb_texture Starfruit_L3`
3. the chosen corrections were written into manifests

What is not done yet:

1. full per-model preview validation for all `3DVA` objects
2. full per-model preview validation for all `MeshMamba non_texture` objects
3. full per-model preview validation for all `MeshMamba rgb_texture` objects
4. a proper `SAL3D` video-vs-preview validation track

So the correct project status is:

1. image-validation workflow is complete
2. representative validation is complete
3. full dataset-wide validation is not complete

#### 3DVA bunny

Final chosen corrective recipe:

1. `recenter_to_bbox_center = true`
2. `extra_rotate_x_deg = -45.0`
3. `override_fov_deg = 37.5`

Manifest:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_3dva_bunny.json`

Final comparison image:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/output_local/preview_checks/3DVA/bunny_frame000_recenter_fov37p5_rotxm45_compare.png`

Interpretation:

This removed the earlier obvious orientation mismatch. It is not a proof that
all 3DVA models need `rotX=-45`; this was a model-specific fix for `bunny`.

#### MeshMamba non_texture Starfruit_L3

Final chosen corrective recipe:

1. `recenter_to_bbox_center = true`
2. `extra_rotate_x_deg = 90.0`
3. `override_fov_deg = 37.5`

Manifest:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_meshmamba_non_texture_starfruit.json`

Final comparison image:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/output_local/preview_checks/MeshMamba_non_texture/Starfruit_L3_frame000_recenter_rotx90_fov37p5_compare.png`

Interpretation:

Vertical orientation is much closer than before. This is currently a pilot
recipe for `Starfruit_L3`, not a guaranteed dataset-wide constant.

#### MeshMamba rgb_texture Starfruit_L3

Current validation uses geometry-only preview, not textured rendering.

Final chosen corrective recipe:

1. `recenter_to_bbox_center = true`
2. `extra_rotate_x_deg = 90.0`
3. `override_fov_deg = 37.5`

Manifest:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_meshmamba_rgb_texture_starfruit.json`

Final comparison image:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/output_local/preview_checks/MeshMamba_rgb_texture/Starfruit_L3_frame000_geometry_only_recenter_rotx90_fov37p5_compare.png`

Interpretation:

For phase 1, geometry-only preview was accepted by the user. This checks pose,
scale impression, and silhouette alignment, not texture faithfulness.

### Where The Checked Images Live

These were the concrete outputs used to make the earlier decisions:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/output_local/preview_checks/3DVA/bunny_frame000_recenter_fov37p5_rotxm45_compare.png`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/output_local/preview_checks/MeshMamba_non_texture/Starfruit_L3_frame000_recenter_rotx90_fov37p5_compare.png`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/output_local/preview_checks/MeshMamba_rgb_texture/Starfruit_L3_frame000_geometry_only_recenter_rotx90_fov37p5_compare.png`

If continuing image validation on more models, inspect these files first and
reuse the same manifest-based process.

### How The Previous Agent Chose The Corrections

The previous agent did not guess the final transforms from theory alone.

The decision process was:

1. render initial preview directly from `json`
2. compare against real video frame
3. if orientation was wrong, sweep/test `extra_rotate_x_deg`
4. if pivot/origin behavior looked wrong, test `recenter_to_bbox_center`
5. if size in frame was wrong, test `override_fov_deg`
6. keep `json` matrices and object placement as the base source of truth
7. only after visual confirmation, write the override into the manifest

The next agent must follow the same logic if new models are calibrated.

### Important Constraint About FOV

Do not assume `37.5` is a dataset-wide constant for all MeshMamba models.

Correct policy:

1. default to FOV from `json`
2. use `override_fov_deg` only as a model-specific override after preview
   validation
3. current `37.5` is validated for the representative `Starfruit_L3` pilot

### Important Constraint About Rotation

Do not generalize the currently chosen `extra_rotate_x_deg` values to entire
datasets without visual validation on more than one object.

Known validated cases so far:

1. `bunny` used `rotX=-45`
2. `Starfruit_L3` used `rotX=90`

These are currently model-level validated overrides, not proven dataset-wide
constants.

## What Was Achieved For Server Preparation

### Server Profile

SSH alias:

`vg-intellect`

No sudo.

Server work root:

`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING`

Server env root:

`/home/29d_kon@lab.graphicon.ru/ssd1_link/environments`

Server datasets root:

`/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets`

### Server Repos

The previous agent already executed remote clone/update commands.

Last known server state:

1. `Mesh-Saliency-Projection` cloned in server work root
2. checked out to branch `reproject-benchmark`
3. up to date with commit `9a55147`
4. `MAMBA_GAZE` cloned separately in server work root
5. checked out to commit `42eb4fc`

Expected server paths:

`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection`

`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/MAMBA_GAZE`

### Why There Are Two Repositories

Do not conflate these two codebases.

`Mesh-Saliency-Projection` currently owns:

1. repo-local preview flow
2. 3DVA wrappers
3. server manifests
4. side-input transfer helpers
5. orchestration around pilot runs

`MAMBA_GAZE` currently owns:

1. actual MeshMamba face-level pipeline
2. `run_meshmamba_gaze.py`
3. `mamba_gaze` package internals

The main repo does not replace `MAMBA_GAZE`; it orchestrates it.

### Server Environment

The previous agent started creating:

`/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark`

Packages intended:

1. `python=3.11`
2. `numpy`
3. `pandas`
4. `scipy`
5. `pillow`
6. `pip`
7. `torch` via CPU wheel

Important uncertainty:

The user interrupted the turn while this remote installation was running.
You must verify whether the env creation finished successfully before using it.

Recommended verification command:

```bash
ssh vg-intellect '
set -euo pipefail
CONDA_BIN="$HOME/miniconda3/bin/conda"
ENV_DIR="/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark"
"$CONDA_BIN" run -p "$ENV_DIR" python - << "PY"
import numpy, pandas, scipy, PIL, torch
print("numpy", numpy.__version__)
print("pandas", pandas.__version__)
print("scipy", scipy.__version__)
print("PIL", PIL.__version__)
print("torch", torch.__version__)
print("cuda", torch.cuda.is_available())
PY
'
```

If this fails, repair the env first.

### Real Dependency Set For Current Pilot Path

Do not trust only the lightweight text requirement files as a complete runtime
description.

Operationally, the current pilot path needs at least:

1. `python`
2. `numpy`
3. `pandas`
4. `scipy`
5. `pillow`
6. `torch`

Reason:

`MAMBA_GAZE/mamba_gaze/pipeline.py` imports `torch` directly.

## Side-Input Transfer Status

### Scripts Already Prepared In Repo

Read these first:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/README.md`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/inventory_3dva.sh`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/inventory_meshmamba_non_texture.sh`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/pack_3dva.sh`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/pack_meshmamba_non_texture.sh`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/scp_archives.sh`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/side_inputs/unpack_on_server.sh`

### Side-Input Archive Results

Local archives were successfully built by the previous agent at:

`/private/tmp/reproject_side_inputs_ready`

Last known sizes:

1. `3dva_csv.tar.gz` ≈ `8.1M`
2. `3dva_json.tar.gz` ≈ `476K`
3. `meshmamba_non_texture_csv.tar.gz` ≈ `18M`
4. `meshmamba_non_texture_json.tar.gz` ≈ `1.5M`

Total compressed size ≈ `29M`

This means `scp` should be fast enough. No need to use GitHub for these data.

At handoff time, these archives existed locally and were ready, but server-side
copy/unpack must still be verified explicitly. Do not assume the transfer
already happened.

### Transfer Policy

Code:

1. `Mesh-Saliency-Projection` via GitHub
2. `MAMBA_GAZE` via GitHub

Side inputs:

1. `csv`
2. `json`

via:

1. local `tar.gz`
2. `scp`
3. server unpack

### Important Rules

1. `json` transfer is mandatory
2. do not start full benchmark before unpack verification
3. do not run `scp` blindly; use dry-run first if needed

### Dry Run Support

`scp_archives.sh` has a dry-run mode.

Example:

```bash
export LOCAL_PACK_DIR=/private/tmp/reproject_side_inputs_ready
export SSH_HOST=vg-intellect
export REMOTE_SIDE_INPUTS=/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs
export DRY_RUN=1
bash test/side_inputs/scp_archives.sh
```

## Current Pilot Launch Wrappers

### 3DVA

Wrapper:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_3dva_pilot.sh`

Important behavior:

1. low priority via `nice`
2. object-level parallel pool
3. `WORKERS=12` default
4. no nested parallelism

### MeshMamba non_texture

Wrapper:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_meshmamba_non_texture_pilot.sh`

Important behavior:

1. calls external `MAMBA_GAZE/run_meshmamba_gaze.py`
2. uses real CLI, not placeholder
3. GT path points to `SaliencyMap/non_texture`
4. `PILOT_MODEL`, `RECENTER_TO_BBOX_CENTER`, `EXTRA_ROTATE_X_DEG`,
   `OVERRIDE_FOV_DEG` are configurable via env

Important CLI fact:

`run_meshmamba_gaze.py` supports:

1. `--device auto`
2. `--frame-alignment nearest`
3. `--point-weight-mode unit`
4. `--smoothing-mode diffusion`

It does NOT support `--workers`.

Parallelism for MeshMamba must be handled outside this script.

## Methods That Are Safest To Launch First

If the user's immediate goal is simply to start metric computation for methods
that already exist, use the smallest reliable runnable set first.

### 3DVA first-set methods

Use first:

1. `reprojection_methods/cone_projection_on_mesh/eval_vs_gt_visual_attention.py`
2. `reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py`

These are repo-local and already wrapped for pilot use.

### MeshMamba non_texture first-set methods

Use first:

1. `our_pipeline`
2. `our_pipeline + diffusion`
3. `our_pipeline + geodesic_kde`

These are accessed through `run_meshmamba_gaze.py` in `MAMBA_GAZE`.

### Do Not Prioritize First

1. `MeshMamba rgb_texture` full metric runs
2. `SAL3D` benchmark runs
3. migrating every external baseline into the repo before the first pilot works

## Immediate Next Steps For The Next Agent

Do these in order.

### Step 1. Read local logs before touching anything

Read:

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/trash/GPT.md`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/trash/Claude.md`

`/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/trash/NEXT_AGENT_HANDOFF.md`

### Step 2. Verify local repo state

Check:

1. branch is still `reproject-benchmark`
2. whether `trash/Claude.md` has uncommitted content
3. do not overwrite anyone else's changes

### Step 3. Verify server state

Check on `vg-intellect`:

1. server repos exist at expected paths
2. `Mesh-Saliency-Projection` is on `reproject-benchmark`
3. `MAMBA_GAZE` exists and is usable
4. environment `reproject-benchmark` is actually runnable

### Step 4. Transfer side inputs

If server env is okay:

1. use the existing archives in `/private/tmp/reproject_side_inputs_ready`
2. optionally run `DRY_RUN=1` first
3. then real `scp`
4. then run server unpack
5. verify final file counts on server:
   - `3DVA`: `32 csv`, `32 json`
   - `MeshMamba_non_texture`: `105 csv`, `105 json`

### Step 5. Re-check image-validation gate before metrics

Before any metric launch, explicitly confirm:

1. the representative compare images still match the intended manifests
2. the selected transforms are the same ones described in this handoff
3. no one silently changed `override_fov_deg` or `extra_rotate_x_deg`
4. you are not using a model-specific override as if it were dataset-wide

If that check fails, return to preview validation first.

### Step 6. Run first server pilot in tmux

Start with `3DVA` first because it is less coupled.

Then `MeshMamba_non_texture`.

Do not start full multi-dataset benchmark immediately.

### Step 7. Only after pilot succeeds

1. prepare full-run commands
2. consider broader model list
3. only then move to wider metric computation

## Recommended First Commands For The Next Agent

### Verify server env

```bash
ssh vg-intellect '
set -euo pipefail
CONDA_BIN="$HOME/miniconda3/bin/conda"
ENV_DIR="/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark"
"$CONDA_BIN" run -p "$ENV_DIR" python - << "PY"
import numpy, pandas, scipy, PIL, torch
print("ok")
PY
'
```

### Transfer side inputs

```bash
cd /Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection
export LOCAL_PACK_DIR=/private/tmp/reproject_side_inputs_ready
export SSH_HOST=vg-intellect
export REMOTE_SIDE_INPUTS=/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs
export DRY_RUN=1
bash test/side_inputs/scp_archives.sh
```

Then real transfer:

```bash
cd /Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection
export LOCAL_PACK_DIR=/private/tmp/reproject_side_inputs_ready
export SSH_HOST=vg-intellect
export REMOTE_SIDE_INPUTS=/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs
unset DRY_RUN
bash test/side_inputs/scp_archives.sh
```

### Unpack on server

```bash
ssh vg-intellect '
set -euo pipefail
source /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection/configs/server_vg_intellect.env
bash /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection/test/side_inputs/unpack_on_server.sh
'
```

### First 3DVA pilot

```bash
ssh vg-intellect '
set -euo pipefail
CONDA_BIN="$HOME/miniconda3/bin/conda"
ENV_DIR="/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark"
REPO="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection"
tmux new-session -d -s reproject-3dva-pilot "
source $REPO/configs/server_vg_intellect.env
$CONDA_BIN run -p $ENV_DIR bash $REPO/test/launch/run_3dva_pilot.sh
"
tmux ls
'
```

### First MeshMamba non_texture pilot

Only after env + side inputs are confirmed.

```bash
ssh vg-intellect '
set -euo pipefail
CONDA_BIN="$HOME/miniconda3/bin/conda"
ENV_DIR="/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark"
REPO="/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection"
export PILOT_MODEL=Starfruit_L3
export RECENTER_TO_BBOX_CENTER=true
export EXTRA_ROTATE_X_DEG=90
export OVERRIDE_FOV_DEG=37.5
tmux new-session -d -s reproject-meshmamba-pilot "
source $REPO/configs/server_vg_intellect.env
export PILOT_MODEL=Starfruit_L3
export RECENTER_TO_BBOX_CENTER=true
export EXTRA_ROTATE_X_DEG=90
export OVERRIDE_FOV_DEG=37.5
$CONDA_BIN run -p $ENV_DIR bash $REPO/test/launch/run_meshmamba_non_texture_pilot.sh
"
tmux ls
'
```

## Warnings

1. The server env creation was interrupted by user abort; verify it.
2. `37.5` for MeshMamba is not globally validated.
3. Do not rewrite `trash/Claude.md`; append only.
4. Do not send anything to server without checking current server state first.
5. Do not assume `MAMBA_GAZE` dependencies are fully described by its
   `requirements.txt`; `torch` is needed in practice.
6. Do not interpret representative image validation as full dataset validation.
7. Do not start `MeshMamba rgb_texture` full benchmark before
   `MeshMamba non_texture` pilot is stable.
8. Do not silently modify geometry recipes and then compare new metrics against
   old numbers as if they were directly comparable.

## What To Tell The User If Asked About Correct Display

Short answer:

1. `bunny` now has a working preview alignment with `recenter + rotX=-45 + FOV 37.5`
2. `Starfruit` in both MeshMamba tracks now has a much better vertical
   orientation with `recenter + rotX=90 + FOV 37.5`
3. all of this is done on top of the original `json` camera/model metadata,
   not instead of it
4. `37.5` is a pilot override, not a universal constant

## If The User Asks Whether The Image-Validation Task Is Done

The correct answer is:

1. the workflow for checking images is implemented and working
2. representative checks are already done for `bunny` and `Starfruit`
3. full per-model validation for all objects is not finished yet

## If The User Asks Whether We Can Start Metrics Now

The correct answer is:

1. yes, for the first pilot set
2. start with the already operational methods:
   - `3DVA`: repo-local cone/geodesic scripts
   - `MeshMamba non_texture`: `run_meshmamba_gaze.py`
3. do not include `SAL3D` yet
4. do not start `MeshMamba rgb_texture` full benchmark before
   `non_texture` pilot succeeds

# Full Run Instructions — 2026-05-30

This file is a detailed operational handoff for continuing the benchmark work
without losing context from the current chat.

It documents:
- what was done,
- what is already validated,
- which datasets/methods are safe to run now,
- exact server paths,
- exact commands,
- known pitfalls,
- what still needs to be checked.

This is written so a human or another model can continue the work end-to-end.

---

## 1. High-level project state

Repository:

- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection`

Branch:

- `reproject-benchmark`

Primary server for benchmark runs:

- `vg-intellect`

Server workspace root:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING`

Server repo path:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection`

Server conda env root:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/environments`

Server Python env actually used for runs:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark`

Current server repo HEAD checked during this chat:

- `9622219`

Important note:

- The server is not necessarily at the newest local `HEAD`.
- For the current `3DVA` and `MeshMamba` runs, this was acceptable because the
  important `3DVA` corrected `-up` OBJ support and the CSV exporter are already
  present in `9622219`.
- Some very recent local-only patches were made later in this chat and were not
  pushed to server yet. These are described below.

---

## 2. Main datasets and current trust level

### 2.1 MeshMamba non_texture

Status:

- Safe for metric runs now.
- Alignment logic is validated.
- We already ran several methods and collected metrics.

Ground truth granularity:

- `per-face`

Safe methods currently used:

- `screen_space_gaussian`
- `cone_gaussian_on_mesh`
- `raycast_nearest_face`
- `our_pipeline+diffusion` via external `MAMBA_GAZE`

Validated representative models already used:

- `Starfruit_L3`
- `Mango_L3`
- `Rubber_Duck_v1_L3`
- `Rhinoceros_v1_L3`

Alignment recipe currently used:

- `recenter_to_bbox_center=true`
- `extra_rotate_x_deg=90`
- `override_fov_deg=37.5`

This recipe is anchored to the MeshMamba render setup and already produced good
IoU alignment during preview validation.

### 2.2 3DVA

Status:

- Safe for metric runs now, provided the corrected OBJ files are used.

Ground truth granularity:

- `per-vertex`

Safe methods currently used:

- `raycast_nearest_vertex`
- `cone_gaussian_on_mesh`

Critical correction:

- Use `3DModels-Simplif-up`
- Do not use old `3DModels-Simplif`

Correct runtime alignment recipe:

- `recenter_to_bbox_center=true`
- `extra_rotate_x_deg=0`
- `override_fov_deg=null` (use FOV from JSON)

This is the important change that fixed the bad `bunny/chair107` overlays.

Local validation summary from corrected `-up` OBJ set:

- mean IoU across 32 models: about `0.946`
- examples:
  - `bunny`: `0.978`
  - `chair107`: `0.933`
  - `flowerpot`: `0.956`
  - `A380`: `0.907`

Important:

- Old manifests such as `preview_3dva_bunny.json`, `preview_3dva_chair107.json`,
  `preview_3dva_flowerpot.json` are legacy and based on wrong OBJ files.
- Correct preview manifests are the `*_up.json` ones, e.g.
  `preview_3dva_bunny_up.json`.

### 2.3 SAL3D

Status:

- Not part of the current safe benchmark run.
- There are local dirty files related to SAL3D. Do not mix them into the
  current `3DVA/MeshMamba` benchmark work unless explicitly requested.

---

## 3. What was already implemented in this chat

### 3.1 Server/runtime prep

Prepared and used:

- `configs/server_vg_intellect.env`
- `test/launch/run_metric_preflight.sh`

Preflight checks already verified on server:

- runtime python exists
- imports:
  - `numpy`
  - `pandas`
  - `scipy`
  - `trimesh`
  - `sklearn`
  - `rtree`
- dataset paths exist
- side input paths exist
- `MAMBA_GAZE/run_meshmamba_gaze.py` exists

### 3.2 CSV exporter

Added:

- `test/tools/export_metrics_csv.py`

Purpose:

- flatten `*_report.json`
- flatten `metrics_vs_gt.json`
- produce table-friendly CSV

This is the current canonical way to build spreadsheet-ready result files.

### 3.3 Lowercase / case-insensitive / alias resolution patch

Local code was edited in this chat to make file matching more robust:

- `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py`
- `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py`
- `reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/mamba_gaze/name_mapping.py`

What those local edits do:

- internal lookup becomes case-insensitive
- file stems are matched in lowercase for resolution
- MeshMamba model aliasing becomes more tolerant
- special case like `Pear_L3` can be resolved toward `Pear.csv`

Important:

- These edits were made locally.
- They were syntax-checked via `python3 -m py_compile`.
- They were **not** pushed to the server during this chat.
- Therefore the server run currently used the older, still working version
  (`9622219`) without this patch.

Implication:

- Current `3DVA` results are unaffected.
- Current `MeshMamba` results for models with already matching names are fine.
- The `Pear_L3` mismatch issue on server will require pushing these changes if
  you want a clean `Pear` run.

---

## 4. Exact server paths in use

### 4.1 Repo

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection`

### 4.2 Output roots used in this chat

MeshMamba outputs:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture`

General CSV summary:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/metrics_summary.csv`

Focused MeshMamba CSV created in this chat:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/metrics_summary_meshmamba_non_texture_focus.csv`

Separate 3DVA top10 run outputs:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone`

Separate 3DVA top10 CSV:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/metrics_summary_3dva_top10.csv`

### 4.3 Datasets on server

3DVA dataset root:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/3DVA`

Critical corrected OBJ subdir:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/3DVA/3DModels-Simplif-up`

3DVA GT:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/3DVA/FixationMaps`

MeshMamba dataset root:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency`

MeshMamba non-texture mesh dir:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/MeshFile/non_texture`

MeshMamba non-texture GT dir:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/MeshMambaSaliency/SaliencyMap/non_texture`

### 4.4 Side inputs on server

3DVA CSV:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/3DVA/csv`

3DVA JSON:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/3DVA/json`

MeshMamba CSV:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/MeshMamba_non_texture/csv`

MeshMamba JSON:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/side_inputs/MeshMamba_non_texture/json`

External pipeline root:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/MAMBA_GAZE`

---

## 5. Meaning of 3DVA GT 300 / 413 / 599

For `3DVA`, each model has three GT maps:

- `<model>_300norm.txt`
- `<model>_413norm.txt`
- `<model>_599norm.txt`

These are:

- not participant counts
- not sample counts
- not view indices in the sense of one fixed camera snapshot

They are:

- IDs of experiment conditions
- tied to different object presentation / rotation conditions

As documented in:

- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/README.md`

Specifically:

- `300 / 413 / 599` are condition IDs
- the README states these correspond to different speeds and/or directions of
  rotation

Practical implication:

- each prediction is compared separately against all 3 GT variants
- the output CSV therefore contains 3 rows per model per method for 3DVA

---

## 6. What was already run successfully

### 6.1 MeshMamba non_texture — completed focused comparison

Models fully prepared and summarized:

- `Starfruit_L3`
- `Mango_L3`
- `Rubber_Duck_v1_L3`
- `Rhinoceros_v1_L3`

Methods used:

- `screen_space_gaussian`
- `cone_gaussian_on_mesh`
- `our_pipeline+diffusion`

Focused CSV:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/metrics_summary_meshmamba_non_texture_focus.csv`

This file is clean and does not mix `3DVA`.

### 6.2 3DVA — top10 run started in separate output root

Requested top10 set:

- `A380`
- `bunny`
- `dragon`
- `chair107`
- `flowerpot`
- `car-vasa`
- `fandisk`
- `casting`
- `turbine`
- `hand-35K`

Run output root:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone`

At the time of writing this file, already finished models were:

- `bunny`
- `car-vasa`
- `chair107`
- `dragon`
- `fandisk`
- `flowerpot`

The run may continue beyond this depending on whether the server process is still active.

3DVA top10 CSV currently available:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/metrics_summary_3dva_top10.csv`

This CSV currently contains rows for the finished subset only.

---

## 7. How to run things

### 7.1 Connect to server

```bash
ssh vg-intellect
```

### 7.2 Enter repo and load env

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
source configs/server_vg_intellect.env
```

### 7.3 Optional: start tmux

```bash
tmux new -s reproject_run
```

### 7.4 Preflight check

```bash
bash test/launch/run_metric_preflight.sh
```

This validates:

- runtime python
- required imports
- datasets
- side inputs
- external MeshMamba pipeline location

### 7.5 MeshMamba single-model runs

#### screen_space

```bash
PILOT_MODEL=Starfruit_L3 bash test/launch/run_meshmamba_baseline_screen_space.sh
```

#### cone/raycast face-level baseline

```bash
PILOT_MODEL=Starfruit_L3 bash test/launch/run_meshmamba_baseline_cone.sh
```

#### our_pipeline + diffusion

```bash
PILOT_MODEL=Starfruit_L3 SMOOTHING_MODE=diffusion bash test/launch/run_meshmamba_non_texture_pilot.sh
```

### 7.6 3DVA batch run

Important:

- use corrected `-up` OBJ files
- use `recenter=true`
- use `extra_rotate_x_deg=0`
- do not override FOV; use JSON

Example:

```bash
OUTPUT_ROOT=/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530 \
NICE_LEVEL=10 \
WORKERS=4 \
RECENTER_TO_BBOX_CENTER=true \
EXTRA_ROTATE_X_DEG=0 \
OVERRIDE_FOV_DEG= \
PILOT_OBJECTS="A380 bunny dragon chair107 flowerpot car-vasa fandisk casting turbine hand-35K" \
bash test/launch/run_3dva_raycast_cone.sh
```

### 7.7 Rebuild CSV summaries

#### MeshMamba focused CSV

```bash
/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark/bin/python \
test/tools/export_metrics_csv.py \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_screen_space/Starfruit_L3/sigma0p05_recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_screen_space/Mango_L3/sigma0p05_recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_screen_space/Rubber_Duck_v1_L3/sigma0p05_recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_screen_space/Rhinoceros_v1_L3/sigma0p05_recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_cone/Starfruit_L3/recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_cone/Mango_L3/recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_cone/Rubber_Duck_v1_L3/recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/baseline_cone/Rhinoceros_v1_L3/recenter_rotx90p0_fov37p5 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/pilot/Starfruit_L3 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/pilot/Mango_L3 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/pilot/Rubber_Duck_v1_L3 \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_non_texture/pilot/Rhinoceros_v1_L3 \
  --output-csv /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/metrics_summary_meshmamba_non_texture_focus.csv
```

#### 3DVA top10 CSV

```bash
/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark/bin/python \
test/tools/export_metrics_csv.py \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone \
  --output-csv /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/metrics_summary_3dva_top10.csv
```

---

## 8. How to monitor progress

### 8.1 Check current server repo head

```bash
ssh vg-intellect
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
git rev-parse --short HEAD
```

### 8.2 Check 3DVA report creation

```bash
find /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone -name '*_report.json' -maxdepth 3 | sort
```

### 8.3 Watch report creation live

```bash
watch -n 5 "find /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone -name '*_report.json' -maxdepth 3 | sort"
```

### 8.4 Check logs

```bash
tail -n 40 /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone/bunny_run.log
```

or:

```bash
for f in /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone/*_run.log; do
  echo "=== $(basename "$f") ==="
  tail -n 10 "$f"
done
```

### 8.5 Check active processes

```bash
pgrep -af "eval_3dva_raycast_cone.py|run_meshmamba_gaze.py|eval_meshmamba_cone.py|eval_meshmamba_screen_space.py"
```

---

## 9. Current result snapshots

### 9.1 3DVA — already finished subset

At one checkpoint in this chat the finished models in the top10 run were:

- `bunny`
- `car-vasa`
- `chair107`
- `dragon`
- `fandisk`
- `flowerpot`

Example comparison for `GT 413`:

#### raycast

- `bunny`: `CC=0.246`, `SIM=0.273`, `KLD=10.797`
- `car-vasa`: `CC=0.236`, `SIM=0.318`, `KLD=8.559`
- `chair107`: `CC=0.059`, `SIM=0.247`, `KLD=12.144`
- `dragon`: `CC=0.147`, `SIM=0.202`, `KLD=11.609`
- `fandisk`: `CC=-0.074`, `SIM=0.163`, `KLD=13.589`
- `flowerpot`: `CC=0.075`, `SIM=0.213`, `KLD=11.254`

#### cone

- `bunny`: `CC=0.354`, `SIM=0.343`, `KLD=1.446`
- `car-vasa`: `CC=0.412`, `SIM=0.327`, `KLD=1.347`
- `chair107`: `CC=0.274`, `SIM=0.376`, `KLD=1.147`
- `dragon`: `CC=0.234`, `SIM=0.216`, `KLD=1.966`
- `fandisk`: `CC=-0.062`, `SIM=0.252`, `KLD=2.139`
- `flowerpot`: `CC=0.134`, `SIM=0.254`, `KLD=1.726`

Observed pattern:

- `cone` is generally much better than `raycast` on these models, especially by `KLD`.

### 9.2 MeshMamba — focused comparison already completed

The focused 4-model file:

- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/metrics_summary_meshmamba_non_texture_focus.csv`

contains:

- `Starfruit_L3`
- `Mango_L3`
- `Rubber_Duck_v1_L3`
- `Rhinoceros_v1_L3`

Methods:

- `screen_space_gaussian`
- `cone_gaussian_on_mesh`
- `our_pipeline+diffusion`

---

## 10. Important known issues

### 10.1 Server is not latest local HEAD

Server checked in this chat:

- `9622219`

This is sufficient for the current `3DVA` run, but not equal to the newest local
working tree.

### 10.2 Local working tree is dirty due to unrelated SAL3D work

Do not blindly commit everything.

At the time of this chat there were unrelated dirty/untracked files such as:

- `DATA_PATHS.md`
- `test/blender_canonical/render_preview_from_manifest_blender.py`
- many `test/manifests/preview_sal3d_*.json`
- `test/tools/generate_sal3d_jsons.py`
- `test/tmp_manifests/`

These were intentionally not mixed into the benchmark commit flow.

### 10.3 Server-side exact mask overlay for 3DVA is not fully set up

The exact local-style mask check on server needs:

- `blender` available on server
- `3DVA_*.mp4` videos present on server

At the time of this chat:

- `ffmpeg` existed on server
- overlay and blender scripts existed on server
- `blender` was not found in `PATH`
- `3DVA_bunny.mp4` was not found under the checked server paths

Meaning:

- exact server-side mask overlay cannot yet be run in the same way as local
  until videos and Blender are available there

### 10.4 Pear / alias problem

Without the local alias patch, `Pear_L3` may fail GT matching on server because:

- CSV/OBJ/JSON use `Pear_L3`
- GT may be named `Pear.csv`

The local patch in this chat was intended to resolve that.

---

## 11. If you want to finish the current 3DVA top10 run

1. Check which report files exist:

```bash
find /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone -name '*_report.json' -maxdepth 3 | sort
```

2. If all 10 reports exist, rebuild CSV:

```bash
/home/29d_kon@lab.graphicon.ru/ssd1_link/environments/reproject-benchmark/bin/python \
  /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection/test/tools/export_metrics_csv.py \
  --input /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/3DVA/raycast_cone \
  --output-csv /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_3dva_top10_20260530/metrics_summary_3dva_top10.csv
```

3. Then summarize separately:

- `raycast_nearest_vertex`
- `cone_gaussian_on_mesh`

Prefer comparing them at:

- `gt_view=413`

because that already showed useful differentiation during this chat.

---

## 12. If you want a full 3DVA run later

Use the same corrected recipe:

- `3DModels-Simplif-up`
- `recenter=true`
- `extra_rotate_x_deg=0`
- `override_fov_deg` omitted

Do not reintroduce old per-model hand-tuning from legacy manifests.

The whole point of the corrected `-up` meshes is that the geometry itself is
already pre-rotated into the canonical orientation.

---

## 13. Minimal “do not forget” checklist

- Do not use old `3DModels-Simplif` for 3DVA.
- Do not use legacy non-`_up` preview manifests for 3DVA alignment decisions.
- Do not mix SAL3D dirty files into current commits.
- Do not assume server is latest local HEAD.
- For `3DVA`, `300/413/599` are condition IDs, not sample counts.
- For `MeshMamba`, GT is per-face.
- For `3DVA`, GT is per-vertex.
- Rebuild CSVs after each batch run; do not rely only on scattered JSON files.

---

## 14. Most useful files to read first

Local repo:

- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/README.md`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/DATA_PATHS.md`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/PIPELINE.md`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_metric_preflight.sh`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_3dva_raycast_cone.sh`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_meshmamba_baseline_cone.sh`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_meshmamba_baseline_screen_space.sh`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_meshmamba_non_texture_pilot.sh`
- `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/tools/export_metrics_csv.py`

External local pipeline:

- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/run_meshmamba_gaze.py`
- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/MAMBA_GAZE/mamba_gaze/name_mapping.py`

Dataset/context docs:

- `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/README.md`


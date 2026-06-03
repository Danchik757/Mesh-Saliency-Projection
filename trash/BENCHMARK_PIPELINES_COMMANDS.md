# Benchmark Pipelines And Commands

Last updated: 2026-06-03 MSK.

This file explains how to run the project. It assumes the reader has already
read `trash/PROJECT_CONTEXT_DATASETS_SERVERS.md` and
`trash/DATASET_STRUCTURE_AUDIT.md`.

## 1. Environment Setup

### Local

Local repo:

```bash
cd '/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection'
```

For local paths, use:

```bash
source test/env/local_paths.sh
```

Some local runs used:

```text
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3
```

If using local Blender:

```text
/Applications/Blender.app/Contents/MacOS/Blender
```

### Server

Connect:

```bash
ssh vg-intellect
```

Repo:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
```

Load env:

```bash
source configs/server_vg_intellect.env
```

Check Python:

```bash
"$REPROJECT_PYTHON" --version
"$REPROJECT_PYTHON" -c "import trimesh, numpy; print('ok')"
```

Use `tmux` for anything long:

```bash
tmux new -s meshmamba_full
tmux attach -t meshmamba_full
```

Run low priority:

```bash
nice -n 10 "$REPROJECT_PYTHON" ...
nice -n 15 "$REPROJECT_PYTHON" ...
```

Avoid `/tmp` for large files on server. Prefer:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/tmp_launchers
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs
```

When counting copied side inputs on `vg-intellect`, ignore macOS AppleDouble
files:

```bash
find "$DIR" -maxdepth 1 -type f ! -name '._*' | wc -l
```

## 2. Preview and Alignment Pipeline

### Purpose

Before metrics, render a preview frame or overlay to verify that:

- object pose matches video
- scale matches video
- frame/time alignment is correct
- FOV interpretation is correct
- JSON camera/object metadata is being used

### Fast manifest preview

Run one manifest:

```bash
bash test/launch/run_preview_manifest.sh test/manifests/preview_meshmamba_non_texture_rubber_duck.json
```

Run a suite:

```bash
bash test/launch/run_preview_suite.sh
```

### Blender canonical preview

Use Blender when exact video matching matters:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/blender_canonical/render_preview_from_manifest_blender.py" \
  -- \
  --manifest "/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/manifests/preview_3dva_bunny.json"
```

Evaluate mask overlay batch:

```bash
python3 test/blender_canonical/evaluate_blender_mask_batch.py \
  --output-dir test/output_local/blender_mask_batch_example \
  --manifest test/manifests/preview_meshmamba_non_texture_starfruit.json
```

### Video overlay tools

Overlay/video comparison scripts:

```text
test/overlay_alignment/overlay_video_and_preview.py
test/overlay_alignment/search_preview_alignment.py
test/tools/make_preview_overlay.py
```

GT/prediction visualization scripts:

```text
test/gt_visualizations/preview_meshmamba_screenspace_alignment.py
test/gt_visualizations/preview_meshmamba_cone_alignment.py
test/gt_visualizations/preview_sal3d_screenspace_alignment.py
test/gt_visualizations/generate_meshmamba_worst_case_bundle.py
```

Example MeshMamba cone preview smoke:

```bash
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 \
  test/gt_visualizations/preview_meshmamba_cone_alignment.py \
  --model Starfruit_L3 \
  --texture-type non_texture \
  --max-frames 12 \
  --output-dir test/output_local/preview_meshmamba_cone_starfruit_smoke_quick
```

Example MeshMamba screen-space preview smoke:

```bash
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 \
  test/gt_visualizations/preview_meshmamba_screenspace_alignment.py \
  --model Starfruit_L3 \
  --texture-type non_texture \
  --preview-frames 138 \
  --output-dir test/output_local/preview_meshmamba_screen_starfruit_smoke
```

## 3. MeshMamba Reference Benchmark

### Dataset and GT

Dataset root:

```text
MeshMambaSaliency
```

GT:

```text
SaliencyMap/non_texture/*.csv
SaliencyMap/rgb_texture/*.csv
```

Prediction output:

- per-face maps
- `*_cone_faces.txt`
- `*_screen_space_faces.txt`

### Current canonical recipe

Use this geometry/camera recipe:

```text
--recenter-to-bbox-center
--extra-rotate-x-deg 90
--projection-fov-mode horizontal_to_vertical
--transform-order blender_rig
```

For screen-space:

```text
--sigma-screen 0.05
```

For cone:

```text
--sigma-deg 1.0
--radius-sigma-mult 3.0
```

### Single method launchers

Cone:

```bash
bash test/launch/run_meshmamba_baseline_cone.sh
```

Screen-space:

```bash
bash test/launch/run_meshmamba_baseline_screen_space.sh
```

These launchers are useful for pilots. For full benchmark use the batch runner.

### Full batch runner

Script:

```text
test/launch/run_meshmamba_reference_batch.py
```

Server command shape:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
source configs/server_vg_intellect.env

nice -n 10 "$REPROJECT_PYTHON" test/launch/run_meshmamba_reference_batch.py \
  --texture-types non_texture rgb_texture \
  --methods cone screen_space \
  --workers 4 \
  --batch-output-dir /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601
```

Actual server output:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601
```

Local archive:

```text
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/
```

Main local CSVs:

```text
meshmamba_reference_long.csv
meshmamba_reference_wide.csv
meshmamba_reference_summary.csv
meshmamba_model_metrics_compact.csv
```

Selected 20-model CSVs generated later:

```text
meshmamba_selected_20_models_metrics.csv
meshmamba_selected_20_models_metrics_compact.csv
meshmamba_selected_20_models_non_texture_metrics_compact.csv
meshmamba_selected_20_models_rgb_texture_metrics_compact.csv
```

Validation of selected CSVs:

- compared against original compact CSV
- compared against original long CSV
- errors: 0

## 4. SAL3D Reference Benchmark

### Dataset and GT

Current server release root:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D
```

Side roots:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/jsons_for_models/SAL3D_json
/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Smooth_Gaze
```

GT source:

- `Gaze/*.txt`
- current scripts use `gt_column=6`
- `Smooth_Gaze` is used when available

### Full batch runner

Script:

```text
test/launch/run_sal3d_reference_batch.py
```

Actual server command shape used:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
source configs/server_vg_intellect.env

export SAL3D_DATASET_ROOT=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D
export SAL3D_CSV_ROOT=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/gaze_csv/SAL3D
export SAL3D_JSON_ROOT=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/jsons_for_models/SAL3D_json
export SAL3D_SMOOTH_GAZE_DIR=/home/29d_kon@lab.graphicon.ru/ssd1_link/datasets/reproject_release_v1/SAL3D/Smooth_Gaze

nice -n 10 "$REPROJECT_PYTHON" test/launch/run_sal3d_reference_batch.py \
  --batch-output-dir /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601 \
  --smooth-gaze-dir "$SAL3D_SMOOTH_GAZE_DIR"
```

Actual server output:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601
```

Local archive:

```text
results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/
```

Main local CSVs:

```text
sal3d_detailed_by_model_method.csv
sal3d_per_model_wide.csv
sal3d_overall_summary.csv
sal3d_model_metrics_compact.csv
sal3d_failed_rows.csv
sal3d_failed_models_concise.csv
```

Expected failures in this run:

- `MaxPlanck`
- `meca`
- `sofa`

Do not treat these as general method failures without checking GT/OBJ size
mismatch first.

## 5. KLD Parameter Sweep

Purpose:

- diagnose why MeshMamba KLD is much higher than SAL3D
- test smoothing parameters, not final benchmark recipe

Main script:

```text
test/kld_parameter_sweep/run_kld_parameter_sweep.py
```

Server launcher:

```text
test/kld_parameter_sweep/server/run_diagnostic_vg_intellect.sh
```

Actual diagnostic server session:

```text
kld_diag_20260602_064256
```

Actual server output:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_diagnostic_20260602_064256
```

Local archive:

```text
results/benchmark_runs/kld_diagnostic/2026-06-02_kld_diagnostic_064256/
```

Key output files:

```text
KLD_DIAGNOSTIC_REPORT.md
kld_sweep_long.csv
kld_sweep_summary.csv
kld_sweep_best_by_model.csv
```

Grid used:

- SAL3D models: `bunny`, `A380`, `dog`, `flowerpot`, `dragon`
- MeshMamba models: `Starfruit_L3`, `Flying_saucer_v1_L3`,
  `Spinning_Top_v1_L3`, `MushroomShitake_L3`, `ball_car_v1_L3`,
  `football_v2_L3`
- texture types: `non_texture`, `rgb_texture`
- methods: `screen_space`, `cone`
- MeshMamba screen sigma: `0.025,0.05,0.075,0.1,0.15,0.2`
- cone sigma/radius grid: sigma `1,2,3,5`, radius `3,5,7`

Run status:

- `306/306` tasks ok

## 6. KLD Postprocess Diagnostic

Purpose:

- do not rerun projection
- load existing prediction maps and GT maps
- recompute metrics under diagnostic post-processing variants

Main script:

```text
test/kld_parameter_sweep/run_kld_postprocess_diagnostics.py
```

Server launcher:

```text
test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh
```

Smoke run:

```bash
RUN_ID=smoke_20260602_081254 MAX_INPUT_ROWS=4 SKIP_DIFFUSION=true NICE_LEVEL=15 \
  bash test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh
```

Full run:

```bash
RUN_ID=full_20260602_081351 NICE_LEVEL=15 \
  bash test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh
```

Actual server session:

```text
kld_postprocess_full_20260602_081351
```

Actual server output:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_postprocess_full_20260602_081351
```

Local archive:

```text
results/benchmark_runs/kld_postprocess/2026-06-02_kld_postprocess_full_081351/
```

Output files:

```text
postprocess_long.csv
postprocess_summary.csv
postprocess_best_by_model.csv
postprocess_top_kld_faces.csv
```

Full run status:

- input maps: 636
- diagnostic rows: 16536
- status: all ok
- failures: 0

Diagnostic variants:

- `baseline`
- `alpha_floor`
- `support_mask`
- `area_weighting`
- `diffusion`

Important: `support_mask` and `alpha_floor` are diagnostics, not automatically
final benchmark methods.

## 7. 3DVA Current Pipeline

Main scripts:

```text
reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py
reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py
test/launch/run_3dva_screen_space.sh
test/launch/run_3dva_raycast_cone.sh
```

Current rules from 2026-06-03 analysis:

- use `3DModels-Simplif-up`
- for screen-space use `sigma_px=49.0`
- compare visible-only metrics when using static 3DVA GT
- do not use 3DVA as primary validation for dynamic gaze

Local smoke result exists for bunny only after the visibility/sigma fixes.
Full 32-model run was not the primary track and should not be presented as
final validation.

Reference doc:

```text
datasets/3DVA_DATASET.md
```

## 8. Geodesic Diffusion

New scripts:

```text
reprojection_methods/cone_projection_on_mesh/eval_meshmamba_geodesic.py
reprojection_methods/cone_projection_on_mesh/eval_sal3d_geodesic.py
```

Status:

- implemented
- local smoke tested on a small subset
- not integrated into full batch runners yet

MeshMamba test output:

```text
results/meshmamba_geodesic_test/
```

SAL3D test output:

```text
results/sal3d_geodesic_test/
```

Example MeshMamba run shape:

```bash
"$PYTHON" reprojection_methods/cone_projection_on_mesh/eval_meshmamba_geodesic.py \
  --model Apple_Red_v1_L3 \
  --texture-type non_texture \
  --dataset-root "$REPROJECT_DATASET_MESHMAMBA_ROOT" \
  --csv-root "$MESHMAMBA_CSV_ROOT" \
  --json-root "$MESHMAMBA_JSON_ROOT" \
  --output-dir results/meshmamba_geodesic_test
```

Example SAL3D run shape:

```bash
"$PYTHON" reprojection_methods/cone_projection_on_mesh/eval_sal3d_geodesic.py \
  --model bunny \
  --dataset-root "$REPROJECT_DATASET_SAL3D_ROOT" \
  --csv-root "$REPROJECT_GAZE_CSV_SAL3D_ROOT" \
  --json-root "$REPROJECT_GAZE_JSON_SAL3D_ROOT" \
  --smooth-gaze-dir "$REPROJECT_SAL3D_SMOOTH_GAZE_ROOT" \
  --output-dir results/sal3d_geodesic_test
```

Important caveat:

- geodesic baseline is vertex cone averaged to faces
- it is not identical to `cone_gaussian_on_mesh` in `eval_meshmamba_cone.py`

## 9. Generating Selected MeshMamba CSVs

Files already created:

```text
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_selected_20_models_metrics.csv
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_selected_20_models_metrics_compact.csv
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_selected_20_models_non_texture_metrics_compact.csv
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_selected_20_models_rgb_texture_metrics_compact.csv
```

The split compact files have the exact same columns as:

```text
meshmamba_model_metrics_compact.csv
```

Validation done:

- header match: true
- compared model rows to original compact: errors 0
- compared model rows to original long: errors 0
- recomputed means: errors 0

Alias used for `Chick`:

```text
Chick -> Bird_v1_L3
```

Reason:

- in full CSV, `Bird_v1_L3` has `gt_file=Chick.csv`

Other aliases used:

```text
egypt_sphinx_iterations-2 -> egypt_sphinx_V2_L3
Horse_v01-it2 -> Horse_v01_L3
WWII_Plane-Germany_Focke-Wulf_FW_190_v1_l3 -> WWII_Plane-Germany_Focke-Wulf_Fw_190_v1
stuffed_animal_L2 -> stuffed_animal_v1_L2
Deathstroke -> Deathstroke-obj
SittingBaby -> SittingBaby_v1_L1
```

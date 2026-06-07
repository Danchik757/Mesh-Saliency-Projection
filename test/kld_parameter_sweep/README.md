# KLD Parameter Sweep Benchmark

This folder contains the standalone benchmark used to diagnose high `KLD` for
`screen_space_gaussian` and `cone_gaussian_on_mesh`.

The benchmark is intentionally separate from the main full-dataset runs. It is
for parameter search and diagnostics, not for the final paper/table unless a
configuration is promoted after review.

## What It Tests

The sweep changes only smoothing-related parameters:

- `screen_space_gaussian`
  - SAL3D: `--sigma-px`
  - MeshMamba: `--sigma-screen`
- `cone_gaussian_on_mesh`
  - `--sigma-deg`
  - `--radius-sigma-mult`

All geometry/camera settings stay fixed to the currently validated Blender-rig
alignment:

- `--recenter-to-bbox-center`
- `--extra-rotate-x-deg 90`
- `--projection-fov-mode horizontal_to_vertical`
- `--transform-order blender_rig`
- SAL3D uses `Smooth_Gaze` when available.

## Why This Exists

`KLD = KL(GT || Pred)` strongly penalizes GT saliency mass that lands on zero or
near-zero prediction. A method can have acceptable `CC`/`SIM` but high `KLD` if
important GT peaks are underpredicted.

The runner therefore writes extra diagnostic fields:

- `gt_mass_on_pred_zero`
- `gt_mass_on_pred_le_1e_8`
- `gt_mass_on_pred_le_1e_6`
- `pred_mass_on_pred_zero`
- `pred_mass_on_pred_le_1e_8`
- `pred_mass_on_pred_le_1e_6`
- `pred_count_zero`
- `pred_count_le_1e_8`
- `pred_count_le_1e_6`
- `top100_kld_contrib_sum`
- `top100_kld_gt_mass`
- `top100_kld_pred_mass`

These fields tell whether high `KLD` is caused by hard zero predictions or by
prediction mass being too weak at GT peaks.

## Files

- `run_kld_parameter_sweep.py`
  - Main Python runner. It launches existing single-model eval scripts and
    aggregates CSVs.
- `configs/nightly_params.env`
  - Default larger overnight parameter grid.
- `configs/sal3d_nightly_models.txt`
  - SAL3D model subset for overnight diagnostics.
- `configs/meshmamba_non_texture_nightly_models.txt`
  - MeshMamba non-texture model subset for overnight diagnostics.
- `server/run_smoke_vg_intellect.sh`
  - Small server smoke test.
- `server/run_nightly_vg_intellect.sh`
  - Starts the overnight sweep in a tmux session.
- `run_kld_postprocess_diagnostics.py`
  - Loads existing MeshMamba `*_faces.txt` prediction maps and recomputes
    metrics under diagnostic post-processing variants.
- `server/run_postprocess_diagnostic_vg_intellect.sh`
  - Starts the post-processing diagnostic in a tmux session.
- `server/schedule_nightly_vg_intellect.sh`
  - Schedules `run_nightly_vg_intellect.sh` for a wall-clock time using `sleep`.
- `server/monitor_vg_intellect.sh`
  - Progress and quick result inspection.

The old entry point still exists as a wrapper:

```bash
test/launch/run_kld_parameter_sweep.py
```

## Outputs

Every run writes:

- `kld_sweep_long.csv`
  - One row per dataset/model/method/parameter set.
- `kld_sweep_summary.csv`
  - Aggregates by dataset/texture/method/parameter set.
- `kld_sweep_best_by_model.csv`
  - Best `KLD` row per dataset/texture/model/method.

Server output paths are under:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/
```

## Server Smoke Test

Run on `vg-intellect` after pulling the branch:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
git pull origin reproject-benchmark
bash test/kld_parameter_sweep/server/run_smoke_vg_intellect.sh
```

Expected result:

- exits with code `0`
- creates `KLD_sweep_smoke_<timestamp>`
- `kld_sweep_long.csv` has all rows with `status=ok`
- diagnostic columns are present

## Overnight Run

Start immediately:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
bash test/kld_parameter_sweep/server/run_nightly_vg_intellect.sh
```

By default, this script starts a new tmux session but waits inside that session
until these current full-run sessions are gone:

```text
sal3d_full_20260601
meshmamba_full_20260601
```

Override this behavior only if you explicitly want overlap:

```bash
WAIT_FOR_SESSIONS="" bash test/kld_parameter_sweep/server/run_nightly_vg_intellect.sh
```

Schedule for 01:00 server time:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
START_AT=01:00 bash test/kld_parameter_sweep/server/schedule_nightly_vg_intellect.sh
```

Monitor:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
bash test/kld_parameter_sweep/server/monitor_vg_intellect.sh
```

## Post-Processing Diagnostic

After the reference MeshMamba run and the focused KLD sweep are complete, run:

```bash
cd /home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/Mesh-Saliency-Projection
bash test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh
```

This does not rerun projection. It loads the existing per-face maps from:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601/
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_diagnostic_20260602_064256/
```

It writes:

- `postprocess_long.csv`
  - One row per source prediction map and diagnostic variant.
- `postprocess_summary.csv`
  - Mean/median metrics by source, texture, method, and variant.
- `postprocess_best_by_model.csv`
  - Best KLD variant per source/texture/model/method/variant family.
- `postprocess_top_kld_faces.csv`
  - Faces contributing most to baseline KLD for manual inspection.

Diagnostic variants:

- `alpha_floor`
  - Adds a small uniform floor to prediction probabilities before KLD.
- `support_mask`
  - Computes metrics on selected face subsets, for example only faces where
    prediction is non-zero.
- `area_weighting`
  - Tests whether GT/prediction should be compared as face mass or face density.
- `diffusion`
  - Smooths prediction over adjacent mesh faces for several step counts.

Use a short smoke run first:

```bash
MAX_INPUT_ROWS=4 SKIP_DIFFUSION=true bash test/kld_parameter_sweep/server/run_postprocess_diagnostic_vg_intellect.sh
```

Interpretation:

- If `alpha_floor` greatly reduces `KLD` while `CC/SIM` stay stable, the main
  issue is likely zero/near-zero predicted mass on GT-positive faces.
- If `support_mask` gives good metrics but baseline does not, prediction support
  is too sparse or GT/prediction support definitions differ.
- If `area_weighting` changes the ranking substantially, the GT and prediction
  maps may use different face mass/density conventions.
- If `diffusion` improves `KLD` without destroying `CC/SIM`, mesh-space
  smoothing should be considered as a promoted method variant.

## Overnight Defaults

The overnight grid in `configs/nightly_params.env` is intentionally larger than
the smoke test:

- SAL3D `screen_space`: 7 sigma values
- MeshMamba `screen_space`: 7 sigma values
- `cone`: 7 sigma values x 4 radius values
- default workers: `24`
- default nice level: `12`
- BLAS thread env vars: `1`

This is enough to identify stable trends without running the entire dataset.

## Interpretation Rules

Do not choose a parameter by `KLD` alone. Prefer configurations that:

- reduce `KLD`
- do not noticeably degrade `CC`
- do not noticeably degrade `SIM`
- reduce `gt_mass_on_pred_zero` and `gt_mass_on_pred_le_1e_8`

If `KLD` improves only because the prediction becomes overly uniform and
`CC/SIM/NSS` degrade, reject that parameter set.

## Current Constraints

- This benchmark is not a replacement for final full-dataset evaluation.
- It should not overwrite existing full-run output folders.
- It should run in a separate tmux session.
- Use `nice` and BLAS thread limits to avoid blocking other users.

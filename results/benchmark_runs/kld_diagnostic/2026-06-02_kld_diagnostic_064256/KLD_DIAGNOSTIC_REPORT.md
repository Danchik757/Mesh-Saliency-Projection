# KLD Diagnostic Report — 2026-06-02

## Purpose

This diagnostic run was launched to understand why `KLD` is much higher on
`MeshMamba` than on `SAL3D`, especially for `screen_space_gaussian`, and to
test whether wider smoothing parameters reduce the amount of GT mass landing on
zero or near-zero prediction regions.

The run was not intended as a final benchmark table. It is a controlled
parameter diagnostic on a small subset of difficult and reference models.

## Server Run

Server:
- `vg-intellect`

Tmux session:
- `kld_diag_20260602_064256`

Server output directory:
- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/KLD_diagnostic_20260602_064256`

Server log:
- `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/tmp_launchers/kld_diag_20260602_064256.log`

Local copied result directory:
- `results/benchmark_runs/kld_diagnostic/2026-06-02_kld_diagnostic_064256/`

Local result files:
- `kld_sweep_long.csv`
- `kld_sweep_summary.csv`
- `kld_sweep_best_by_model.csv`

Launcher added locally:
- `test/kld_parameter_sweep/server/run_diagnostic_vg_intellect.sh`

## Execution Parameters

Parallelism:
- `workers=32`
- `nice=15`
- `OMP_NUM_THREADS=1`
- `OPENBLAS_NUM_THREADS=1`
- `MKL_NUM_THREADS=1`
- `NUMEXPR_NUM_THREADS=1`

Datasets:
- `sal3d`
- `meshmamba`

Methods:
- `screen_space`
- `cone`

SAL3D models:
- `bunny`
- `A380`
- `dog`
- `flowerpot`
- `dragon`

MeshMamba models:
- `Starfruit_L3`
- `Flying_saucer_v1_L3`
- `Spinning_Top_v1_L3`
- `MushroomShitake_L3`
- `ball_car_v1_L3`
- `football_v2_L3`

MeshMamba texture types:
- `non_texture`
- `rgb_texture`

SAL3D `screen_space` sigma grid:
- `6.575`
- `13.15`
- `26.3`
- `39.45`
- `52.6`
- `78.9`

MeshMamba `screen_space` sigma grid:
- `0.025`
- `0.05`
- `0.075`
- `0.1`
- `0.15`
- `0.2`

Cone grid:
- `sigma_deg = 1, 2, 3, 5`
- `radius_sigma_mult = 3, 5, 7`

Total tasks:
- `306`

Run status:
- `306 / 306` report JSON files produced
- `306 / 306` CSV rows have `status=ok`
- no runtime errors in this diagnostic run

## CSV Row Counts

`kld_sweep_long.csv`:
- `306` rows

`kld_sweep_summary.csv`:
- `54` rows

`kld_sweep_best_by_model.csv`:
- `34` rows

Breakdown from `kld_sweep_long.csv`:

| Dataset | Texture | Method | Rows |
|---|---|---|---:|
| MeshMamba | `non_texture` | `cone` | 72 |
| MeshMamba | `non_texture` | `screen_space` | 36 |
| MeshMamba | `rgb_texture` | `cone` | 72 |
| MeshMamba | `rgb_texture` | `screen_space` | 36 |
| SAL3D | `-` | `cone` | 60 |
| SAL3D | `-` | `screen_space` | 30 |

## Best Mean Parameters By Group

Best rows below are selected from `kld_sweep_summary.csv` by minimum
`KLD_mean` within each dataset / texture / method group.

| Dataset | Texture | Method | Best Param | KLD Mean | CC Mean | SIM Mean | GT Mass on Pred <= 1e-6 |
|---|---|---|---|---:|---:|---:|---:|
| MeshMamba | `non_texture` | `cone` | `cone_sigma5_radius7` | 0.6842 | -0.1193 | 0.5790 | 0.0000 |
| MeshMamba | `rgb_texture` | `cone` | `cone_sigma5_radius7` | 0.9256 | -0.1892 | 0.5135 | 0.0127 |
| MeshMamba | `non_texture` | `screen_space` | `screen_sigmascreen0p2` | 3.5066 | -0.0865 | 0.5567 | 0.1803 |
| MeshMamba | `rgb_texture` | `screen_space` | `screen_sigmascreen0p2` | 3.8796 | -0.0557 | 0.5301 | 0.1972 |
| SAL3D | `-` | `cone` | `cone_sigma1_radius7` | 0.9996 | 0.3984 | 0.4962 | 0.0007 |
| SAL3D | `-` | `screen_space` | `screen_sigmapx78p9` | 1.6912 | 0.2079 | 0.4483 | 0.0354 |

Important interpretation:
- MeshMamba `cone` improves strongly when the cone kernel is widened.
- MeshMamba `screen_space` remains bad even with the largest tested sigma.
- SAL3D numbers here are not directly comparable to the full SAL3D benchmark
  mean because this diagnostic subset intentionally includes several difficult
  models and uses only a parameter subset.

## Best-By-Model Summary

Rows below are selected from `kld_sweep_best_by_model.csv`, then averaged inside
each dataset / texture / method group.

| Dataset | Texture | Method | Models | Best-By-Model KLD Mean | Best-By-Model KLD Median | Most Frequent Best Params |
|---|---|---|---:|---:|---:|---|
| MeshMamba | `non_texture` | `cone` | 6 | 0.6842 | 0.6468 | `cone_sigma5_radius7`: 5, `cone_sigma5_radius5`: 1 |
| MeshMamba | `rgb_texture` | `cone` | 6 | 0.9256 | 0.9448 | `cone_sigma5_radius7`: 6 |
| MeshMamba | `non_texture` | `screen_space` | 6 | 3.5027 | 3.9730 | `screen_sigmascreen0p2`: 4, `screen_sigmascreen0p1`: 2 |
| MeshMamba | `rgb_texture` | `screen_space` | 6 | 3.8692 | 4.7398 | `screen_sigmascreen0p2`: 4, `screen_sigmascreen0p075`: 1, `screen_sigmascreen0p025`: 1 |
| SAL3D | `-` | `cone` | 5 | 0.9582 | 0.5131 | mixed per-model params |
| SAL3D | `-` | `screen_space` | 5 | 1.6608 | 1.8977 | mixed per-model params |

## High KLD Cases After Best-By-Model Selection

Even after choosing the best parameter per model/method, the worst remaining
rows are mostly MeshMamba `screen_space`:

| Dataset | Texture | Method | Model | Best Param | KLD | GT Mass on Pred <= 1e-6 |
|---|---|---|---|---|---:|---:|
| MeshMamba | `rgb_texture` | `screen_space` | `Spinning_Top_v1_L3` | `screen_sigmascreen0p025` | 5.6408 | 0.2909 |
| MeshMamba | `rgb_texture` | `screen_space` | `Flying_saucer_v1_L3` | `screen_sigmascreen0p075` | 5.5420 | 0.2626 |
| MeshMamba | `rgb_texture` | `screen_space` | `MushroomShitake_L3` | `screen_sigmascreen0p2` | 5.3155 | 0.2893 |
| MeshMamba | `non_texture` | `screen_space` | `Spinning_Top_v1_L3` | `screen_sigmascreen0p2` | 5.1280 | 0.2613 |
| MeshMamba | `non_texture` | `screen_space` | `MushroomShitake_L3` | `screen_sigmascreen0p1` | 5.0005 | 0.2751 |
| MeshMamba | `non_texture` | `screen_space` | `Flying_saucer_v1_L3` | `screen_sigmascreen0p1` | 4.5991 | 0.2279 |
| MeshMamba | `rgb_texture` | `screen_space` | `ball_car_v1_L3` | `screen_sigmascreen0p2` | 4.1641 | 0.2222 |
| MeshMamba | `non_texture` | `screen_space` | `ball_car_v1_L3` | `screen_sigmascreen0p2` | 3.3469 | 0.1797 |
| SAL3D | `-` | `screen_space` | `A380` | `screen_sigmapx13p15` | 2.9163 | 0.1381 |
| MeshMamba | `non_texture` | `screen_space` | `football_v2_L3` | `screen_sigmascreen0p2` | 2.3085 | 0.1154 |

## Interpretation

### 1. MeshMamba cone is under-smoothed in the reference full run

The original full MeshMamba run used:
- `cone_sigma1_radius3`

The diagnostic subset strongly prefers:
- `cone_sigma5_radius7`

For the difficult MeshMamba subset, this reduces mean KLD substantially:
- `non_texture cone`: best diagnostic mean KLD `0.6842`
- `rgb_texture cone`: best diagnostic mean KLD `0.9256`

The most important signal is that `gt_mass_on_pred_le_1e_6` drops near zero for
`non_texture cone` with the wider kernel. This supports the hypothesis that high
KLD was caused by GT mass landing on near-zero prediction regions.

### 2. MeshMamba screen_space remains structurally weak

Increasing screen sigma up to `0.2` did not solve MeshMamba `screen_space`:
- `non_texture screen_space`: best mean KLD `3.5066`
- `rgb_texture screen_space`: best mean KLD `3.8796`

The GT mass on near-zero prediction remains high:
- `0.1803` for `non_texture`
- `0.1972` for `rgb_texture`

This suggests the issue is not just insufficient Gaussian blur in 2D. The
screen-space method likely leaves important GT regions uncovered because of
visibility, projection support, protocol mismatch, face-level GT semantics, or
face-index/domain mismatch.

### 3. KLD alone should not be optimized blindly

For MeshMamba `cone`, the best KLD parameters have negative mean `CC` in this
subset:
- `non_texture cone`: `CC_mean=-0.1193`
- `rgb_texture cone`: `CC_mean=-0.1892`

This means widening the kernel reduces KLD by filling holes, but it may also
damage the shape/rank agreement with GT. The next benchmark should evaluate
multi-metric tradeoff, not only minimum KLD.

### 4. SAL3D diagnostic subset behaves differently from full SAL3D

The full SAL3D reference run previously showed:
- `cone` mean KLD around `0.4514`
- `screen_space` mean KLD around `0.9383`

This diagnostic subset is harder and not intended as the final SAL3D score.
The selected models include difficult cases such as `A380` and `dog`, so the
subset mean is higher.

## Current Hypotheses

1. MeshMamba full-run KLD is high mainly because prediction has zero or near-zero
   probability on faces where GT has non-trivial mass.

2. Wider `cone_gaussian_on_mesh` kernels reduce this zero-support problem, but
   too much smoothing may reduce `CC`, `Spearman`, and semantic localization.

3. MeshMamba `screen_space_gaussian` is not fixed by sigma alone; the problem is
   likely related to projection support, visibility/culling, face mapping, or
   GT protocol compatibility.

4. The MeshMamba GT may not be fully compatible with our video-gaze projection
   protocol, even when visual object alignment is correct.

## Recommended Next Tests

### Test A — Prediction floor / alpha smoothing without rerunning projection

Goal:
- test whether KLD is dominated by exact zero or near-zero prediction mass.

Method:
- reuse existing prediction maps and GT maps
- recompute metrics after:

```text
Pred_prob_smooth = (1 - alpha) * Pred_prob + alpha * Uniform
```

Suggested alpha grid:

```text
0
1e-8
1e-7
1e-6
1e-5
1e-4
1e-3
1e-2
```

Expected interpretation:
- if KLD drops sharply at very small `alpha`, KLD is mostly a support/floor
  problem
- if `CC/SIM/Spearman` remain stable, this is a metric-stability issue
- if KLD only improves with large `alpha`, prediction is genuinely missing large
  GT regions

This test is cheap because it does not require reprojection.

### Test B — Visibility/support mask metrics for MeshMamba

Goal:
- test whether MeshMamba is being penalized on faces that are never visible or
  never reachable by the gaze/video projection.

Metric domains to compare:
- all faces
- prediction nonzero support
- faces visible in at least one frame
- faces hit/projected at least once
- union of visible plus adjacent faces after local dilation

Expected interpretation:
- if metrics improve strongly on visible/projected support, the final benchmark
  needs a visibility-aware protocol
- if metrics remain bad, the issue is more likely GT semantics or face mapping

### Test C — MeshMamba face-area weighting

Goal:
- test whether per-face metrics should be weighted by face area.

Variants:
- current unweighted face vectors
- area-weighted probability normalization
- area-normalized GT before comparison

Why:
- MeshMamba GT is per-face; if GT was produced as surface density but evaluated
  as one value per face, small and large faces may be weighted incorrectly.

Expected interpretation:
- if KLD/CC/SIM change substantially, our metric domain is not aligned with the
  dataset GT convention.

### Test D — Post-projection mesh diffusion / geodesic smoothing

Goal:
- fill local zero-support holes on the mesh without making the projection kernel
  extremely wide in camera space.

Variants:
- face adjacency diffusion with several step counts
- geodesic/graph Gaussian smoothing on faces
- normalize after smoothing

Why:
- `cone_sigma5_radius7` helps KLD but may hurt localization. Surface diffusion
  may fill holes more naturally than a very wide cone.

Expected interpretation:
- if KLD drops while `CC/Spearman` stay higher than with `cone_sigma5_radius7`,
  diffusion is a better method-level improvement.

### Test E — Top-GT / top-pred face visualization for high-KLD models

Goal:
- visually inspect whether GT hotspots and predicted hotspots are on the same
  semantic object regions.

Models:
- `Flying_saucer_v1_L3`
- `Spinning_Top_v1_L3`
- `MushroomShitake_L3`
- `ball_car_v1_L3`
- `football_v2_L3`

Visualizations:
- top 1%, 5%, 10% GT faces
- top 1%, 5%, 10% prediction faces
- top KLD contribution faces
- overlay on the same OBJ using the same face order

Expected interpretation:
- if GT hotspots are semantically different from our video-gaze hotspots, the
  issue is protocol mismatch
- if overlays look shifted or scrambled, investigate face indexing / OBJ-to-GT
  correspondence

### Test F — Face-index compatibility and OBJ target-stem audit

Goal:
- ensure MeshMamba GT face order matches the OBJ actually used in evaluation.

Checks:
- compare GT row count to `mesh.faces`
- resolve symlinks and real OBJ stems
- verify whether GT belongs to the symlink stem or the real target stem
- visualize top GT faces on the exact loaded mesh

Why:
- prior work already found symlink/target stem issues in MeshMamba lookup.
  Remaining high-KLD cases may still have subtle face-order problems.

### Test G — Temporal/frame alignment sensitivity

Goal:
- test whether gaze timestamps and model animation frames are offset.

Variants:
- current nearest-frame mapping
- frame offset `-3, -2, -1, 0, +1, +2, +3`
- interpolation between adjacent JSON rotations

Expected interpretation:
- if metrics improve at a nonzero offset, the CSV/video/JSON timing alignment
  still needs correction
- if no offset helps, timing is probably not the main issue

### Test H — FOV / pose perturbation sanity sweep

Goal:
- verify that metric failure is not caused by small residual camera/FOV mismatch.

Variants:
- FOV around current value
- small `rotX/rotY/rotZ` perturbations
- scale perturbations

Important:
- do not tune final parameters by GT alone
- first use video-mask overlay/IoU to keep the render physically valid

Expected interpretation:
- if visual IoU remains high but GT metrics do not improve, the issue is not
  object placement

### Test I — Full MeshMamba rerun with best cone parameters

Goal:
- verify whether `cone_sigma5_radius7` generalizes beyond the six diagnostic
  MeshMamba models.

Run:
- all `105 non_texture`
- all `105 rgb_texture`
- method: `cone`
- params: `sigma_deg=5`, `radius_sigma_mult=7`

Compare against previous full reference:
- `cone_sigma1_radius3`

Expected interpretation:
- if KLD improves across the full dataset but `CC/Spearman` drop, report a
  multi-metric tradeoff
- if both KLD and rank metrics improve, update the default cone configuration
  for MeshMamba

## Immediate Recommendation

The next cheapest and most informative tests are:

1. `Prediction floor / alpha smoothing` on existing outputs.
2. `Visibility/support mask metrics` on existing outputs.
3. `Top-GT / top-pred / top-KLD visualization` for the five worst MeshMamba
   models.

Only after those should we run another expensive full MeshMamba benchmark with
new method defaults.

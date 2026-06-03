# Results, Issues, Decisions, Next Steps

Last updated: 2026-06-03 MSK.

This file records the current benchmark results and the interpretation rules
that matter for the next agent. It also lists resolved problems and open risks.

Dataset/result counts in this file were cross-checked against:

```text
trash/DATASET_STRUCTURE_AUDIT.md
```

## 1. Current Result Artifacts

### MeshMamba full reference

Local archive:

```text
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/
```

Files:

```text
meshmamba_reference_long.csv
meshmamba_reference_wide.csv
meshmamba_reference_summary.csv
meshmamba_model_metrics_compact.csv
meshmamba_selected_20_models_metrics.csv
meshmamba_selected_20_models_metrics_compact.csv
meshmamba_selected_20_models_non_texture_metrics_compact.csv
meshmamba_selected_20_models_rgb_texture_metrics_compact.csv
```

Server origin:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/MeshMamba_reference_batch_20260601
```

Full run shape:

- 105 models
- 2 texture tracks
- 2 methods
- 420 total rows
- 420 ok
- 0 failed

Summary:

| texture_type | method | n_ok | CC_mean | SIM_mean | KLD_mean | Spearman_mean | hit_rate_mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| non_texture | cone | 105 | 0.3212 | 0.5935 | 0.9635 | 0.2684 | 0.8974 |
| non_texture | screen_space | 105 | 0.1359 | 0.5833 | 1.9539 | 0.1272 | n/a |
| rgb_texture | cone | 105 | 0.2696 | 0.5719 | 1.1570 | 0.2326 | 0.9148 |
| rgb_texture | screen_space | 105 | 0.1290 | 0.5744 | 1.9379 | 0.1275 | n/a |

Interpretation:

- Cone is better than screen-space on KLD/CC/Spearman.
- SIM is similar between methods.
- RGB texture track is not dramatically better than non-texture.
- Metrics are lower than hoped despite good geometry alignment.

### MeshMamba selected 20-model compact files

Files:

```text
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_selected_20_models_non_texture_metrics_compact.csv
results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_selected_20_models_rgb_texture_metrics_compact.csv
```

Validation:

- same columns as `meshmamba_model_metrics_compact.csv`
- 20 model rows + 1 mean row in each file
- compared against original compact and long CSVs
- errors: 0

Selected 20-model means:

| texture_type | cone_CC | cone_SIM | cone_KLD | screen_CC | screen_SIM | screen_KLD |
|---|---:|---:|---:|---:|---:|---:|
| non_texture | 0.3270 | 0.5795 | 1.6145 | 0.1612 | 0.5801 | 2.1936 |
| rgb_texture | 0.2382 | 0.5438 | 2.0533 | 0.1032 | 0.5672 | 2.3012 |

Important alias:

- requested `Chick` maps to source model `Bird_v1_L3`
- reason: source row has `gt_file=Chick.csv`

### SAL3D full reference

Local archive:

```text
results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/
```

Files:

```text
sal3d_detailed_by_model_method.csv
sal3d_per_model_wide.csv
sal3d_overall_summary.csv
sal3d_model_metrics_compact.csv
sal3d_failed_rows.csv
sal3d_failed_models_concise.csv
```

Server origin:

```text
/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs/SAL3D_reference_batch_20260601
```

Full run shape:

- 54 models
- 2 methods
- 108 tasks
- 51 ok models per method
- 3 failed models per method

Known failed models:

- `MaxPlanck`
- `meca`
- `sofa`

Summary:

| method | n_ok | CC_mean | SIM_mean | KLD_mean | Spearman_mean | hit_rate_mean |
|---|---:|---:|---:|---:|---:|---:|
| cone | 51 | 0.4855 | 0.6577 | 0.4514 | 0.4955 | 0.8949 |
| screen_space | 51 | 0.3385 | 0.6179 | 0.9383 | 0.3456 | n/a |

Interpretation:

- SAL3D metrics are much stronger than MeshMamba.
- Cone is clearly better than screen-space.
- This supports SAL3D as the primary current benchmark track.

### KLD parameter sweep

Local archive:

```text
results/benchmark_runs/kld_diagnostic/2026-06-02_kld_diagnostic_064256/
```

Files:

```text
KLD_DIAGNOSTIC_REPORT.md
kld_sweep_long.csv
kld_sweep_summary.csv
kld_sweep_best_by_model.csv
```

Run shape:

- 306 tasks
- all ok
- subset diagnostic, not final benchmark

Key finding:

- Wider cone smoothing improves MeshMamba KLD.
- `cone_sigma5_radius7` was best in the focused MeshMamba sweep.
- Screen-space remained weak even with wider `sigma_screen`.

Important caution:

- Do not select final parameters by KLD alone.
- If KLD improves only because prediction becomes uniform, reject it.

### KLD postprocess diagnostic

Local archive:

```text
results/benchmark_runs/kld_postprocess/2026-06-02_kld_postprocess_full_081351/
```

Files:

```text
postprocess_long.csv
postprocess_summary.csv
postprocess_best_by_model.csv
postprocess_top_kld_faces.csv
```

Run shape:

- 636 input maps
- 16536 diagnostic rows
- all ok
- 0 failures

What was tested:

- baseline recomputation
- `alpha_floor`
- `support_mask`
- `area_weighting`
- `diffusion`
- top-KLD face extraction

Full-reference MeshMamba baseline from this diagnostic:

| texture_type | method | KLD | CC | SIM |
|---|---:|---:|---:|---:|
| non_texture | cone | 0.9635 | 0.3212 | 0.5935 |
| non_texture | screen_space | 1.9539 | 0.1359 | 0.5833 |
| rgb_texture | cone | 1.1570 | 0.2696 | 0.5719 |
| rgb_texture | screen_space | 1.9379 | 0.1290 | 0.5744 |

Diagnostic conclusions:

- `alpha_floor=0.01` greatly lowers KLD with almost no CC/SIM change.
- `support_mask=intersection_positive` gives the lowest KLD, but it is not a
  fair benchmark metric because it changes the evaluation domain.
- `divide_area` strongly raises CC for full-reference MeshMamba, often to about
  0.66-0.70, which suggests face mass vs face density convention needs checking.
- `diffusion_steps40_blend0.5` helps screen-space KLD, but not enough to solve
  the full problem by itself.

Current interpretation:

- MeshMamba high KLD is not best explained by camera alignment alone.
- A large component is zero or near-zero predicted probability on GT-positive
  faces.
- Another likely component is GT/prediction face-area convention.

## 2. Resolved Problems

### MeshMamba object alignment

Problem:

- early previews were too small or incorrectly rotated
- direct JSON FOV use gave bad mask IoU

Resolution:

- use `transform_order=blender_rig`
- recenter to bbox center
- `extra_rotate_x_deg=90`
- interpret stored FOV through `horizontal_to_vertical`
- use JSON camera/object metadata

Validated by:

- high video mask IoU for multiple MeshMamba objects
- server smokes using the same recipe

Remaining caveat:

- good object/video alignment does not imply good GT correlation.

### MeshMamba screen-space back-face culling

Problem:

- screen-space predictions could include back-facing faces

Resolution:

- current MeshMamba screen-space eval performs back-face culling
- reports `culled_back_faces`

### MeshMamba GT file lookup with symlinked OBJ names

Problem:

- some server OBJ paths used symlink or convenience names that did not match GT
  stems

Resolution:

- GT lookup now falls back through resolved OBJ stem
- important for non-standard names such as `MushroomShitake`

### SAL3D camera_world_pos bug

Problem:

- `camera_world_pos` computation was previously inside the per-frame loop in a
  way that made the script inefficient and risky

Resolution:

- fixed before the SAL3D reference run
- verified in Claude session 15 instructions

### 3DVA screen-space sigma bug

Problem:

- old screen-space used fractional `sigma_screen=0.05` on a 256 px map
- equivalent to about 96 px at 1920 width
- too wide for the original 3DVA paper setup

Resolution:

- 3DVA screen-space v2 uses absolute `sigma_px=49.0`
- bilinear deposition/sampling
- visibility masking added

### 3DVA axis/model directory

Problem:

- `3DModels-Simplif` has wrong axis for our use

Resolution:

- use `3DModels-Simplif-up`
- manifest updated

## 3. Open Problems and Risks

### MeshMamba GT mismatch

Status:

- unsolved

Symptoms:

- object/video mask IoU can be high
- hit rate can be high
- metrics against GT remain moderate/low, especially CC/Spearman and KLD

Most likely explanations:

1. GT saliency is much sparser/localized than our accumulated prediction.
2. KLD harshly penalizes zero prediction mass on GT-positive faces.
3. GT CSV values may represent face mass or face density differently from our
   prediction.
4. Some face-index or GT-to-OBJ mapping issue may still exist for specific
   models.

Next checks:

- inspect `postprocess_top_kld_faces.csv`
- visualize top GT faces and top KLD faces on worst models
- verify face-area convention
- decide whether to promote an `alpha_floor` or mesh diffusion variant

### Alpha floor is diagnostic, not automatically final

`alpha_floor=0.01` improves KLD strongly. This might be a valid smoothing prior,
but it must be promoted explicitly and justified. It should not be silently used
as if it were the original method.

If promoted:

- implement it inside eval scripts or a named post-processing method
- rerun full MeshMamba benchmark
- report both baseline and floor-smoothed results

### Support mask metrics are not final benchmark metrics

`intersection_positive` produces very low KLD because it restricts comparison
to faces where both GT and prediction are positive. This is useful to diagnose
support mismatch, but it is not a fair method comparison unless a paper uses the
same support definition.

### Area weighting is unresolved

The `divide_area` diagnostic strongly changes CC. This suggests the GT and
prediction might not be in the same face mass/density convention.

Need to determine:

- does MeshMamba `SaliencyMap/*.csv` store per-face mass?
- does it store per-area density?
- did the original model evaluation normalize by face area?

Do not publish final MeshMamba conclusions before resolving this.

### Geodesic diffusion not integrated

Geodesic scripts exist and smoke tests show modest KLD improvement, but:

- no full batch runner integration yet
- parameters need tuning
- baseline is vertex-cone averaged to faces, not identical to current face-cone

Recommended:

- create separate geodesic batch runners
- run MeshMamba non_texture full first
- then SAL3D full if runtime is acceptable

### 3DVA cannot be primary validation

The 3DVA GT is static-view GT. Our gaze data is dynamic rotating video.

Do not claim:

- "low 3DVA CC means projection failed"
- "high 3DVA CC proves dynamic projection is correct"

Use 3DVA only as:

- external cross-condition reference
- comparison with published methods under same GT
- geometry saliency sanity check

### SAL3D expected failures

The full SAL3D run has 3 known failures:

- `MaxPlanck`
- `meca`
- `sofa`

Do not rerun the whole benchmark just because these failed. Investigate GT/OBJ
vertex mismatch first.

## 4. Recommended Next Steps

### Step 1 - Commit or archive current handoff state

Before handing to another agent:

```bash
git status --short
```

Decide whether to commit:

- new handoff docs
- generated selected CSVs
- KLD postprocess scripts/results
- geodesic scripts

Do not commit generated large artifacts unless intentionally wanted in git.

### Step 2 - Resolve MeshMamba face-area convention

This is the most important technical question.

Actions:

1. Inspect MeshMamba dataset documentation if available.
2. Check whether GT values sum to a fixed total before or after area weighting.
3. Compare correlation under `none`, `multiply_area`, `divide_area`.
4. Visualize top GT and top KLD faces from:

```text
results/benchmark_runs/kld_postprocess/2026-06-02_kld_postprocess_full_081351/postprocess_top_kld_faces.csv
```

Expected outcome:

- decide whether final MeshMamba metrics should use raw face values or
  area-normalized values

### Step 3 - Promote or reject alpha floor

If using KLD as a primary metric, decide whether a small floor is methodologically
acceptable.

Options:

1. Keep baseline only.
2. Add a named method variant:
   - `screen_space_gaussian_alpha_floor`
   - `cone_gaussian_on_mesh_alpha_floor`
3. Report both baseline and alpha-floor side by side.

Do not silently replace baseline KLD.

### Step 4 - Integrate geodesic diffusion as separate batch

Recommended approach:

- do not modify existing reference batch runner first
- create separate batch scripts:
  - `run_meshmamba_geodesic_batch.py`
  - `run_sal3d_geodesic_batch.py`

Reason:

- output keys differ
- sigma parameters differ
- baseline is not identical to existing face-cone

### Step 5 - Use SAL3D as the clean primary comparison

SAL3D currently gives the cleanest numbers and is closest to our video setting.

Next SAL3D work:

- decide whether to handle failed models or keep them documented
- run geodesic/floor variants if promoted
- prepare final table from:

```text
results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_model_metrics_compact.csv
```

### Step 6 - Keep 3DVA separate

Do not mix 3DVA into the main final benchmark table unless explicitly labeled
as cross-condition.

If continuing 3DVA:

- run all 32 models only after deciding the evaluation question
- use visible-only metrics
- compare with `SaliencyAlgorithmMaps` if the goal is published-method comparison

## 5. What Not To Do

Do not:

- use `git reset --hard`
- delete untracked result folders without inspection
- run server jobs without `tmux`
- run large jobs without `nice`
- use `vg-iai` paths for this project
- use 3DVA as primary dynamic-video GT
- tune MeshMamba FOV using GT metrics
- silently apply alpha floor to final metrics
- treat support-mask metrics as final benchmark metrics
- mix SAL3D raw GT and Smooth_Gaze GT without labeling
- compare vertex and face methods without explicit conversion/adaptation note

## 6. Fast Orientation for a New Agent

If you only have 10 minutes:

1. Open `results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_reference_summary.csv`.
2. Open `results/benchmark_runs/sal3d/2026-06-01_sal3d_reference/sal3d_overall_summary.csv`.
3. Open `results/benchmark_runs/kld_postprocess/2026-06-02_kld_postprocess_full_081351/postprocess_summary.csv`.
4. Read the "Open Problems" section in this file.
5. Check `git status --short`.
6. Ask before touching server.

The current high-level conclusion:

- SAL3D benchmark is usable and strong.
- MeshMamba benchmark runs cleanly but has unresolved GT/support/area-convention
  interpretation issues.
- 3DVA is not primary validation for the dynamic-video gaze task.
- Geodesic diffusion is promising but not yet full-batch integrated.

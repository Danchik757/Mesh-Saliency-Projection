# 3DVA Pipeline In This Repository

Last checked: 2026-06-13

This note describes the current 3DVA benchmark path implemented in the repository.
It is intended as an operational reference for agents and server runs.

## Current Contract

3DVA is evaluated against a combined per-vertex GT map. The current default input is
processed participant fixation JSON, not legacy CSV.

Baseline timing contract:

- Participant fixations use full-length offset0 JSON with
  `fixation_format=one_turn_from_start_offset_0`.
- For 17 second tracks, use `gaze[0:450] -> placement[0:450]`.
- The final 60 frames are excluded, leaving one complete 15 second object turn.
- Empty processed fixation files are invalid and the model is excluded. This is
  expected for `3DVA_jessi`.

The report provenance must include:

- `participant_input.input_mode == "processed_json"`
- `participant_input.fixation_format == "one_turn_from_start_offset_0"`
- `participant_input.timing_contract == "one_turn_from_start"`
- `participant_input.frame_offset == 0`
- `participant_input.delay_frames == 0`

Legacy CSV mode still exists only behind `--csv-compat`. It must not be used for
new benchmark runs unless explicitly debugging historical results.

## Main Entry Points

Batch runner:

- `test/launch/run_3dva_reference_batch.py`

Evaluators:

- `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py`
- `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py`

Combined GT builder:

- `scripts/build_3dva_combined_gt.py`

The batch runner writes:

- `3dva_combined_long.csv`
- `3dva_combined_wide.csv`
- `3dva_combined_summary.csv`
- per-model `*_report.json`
- per-model predicted maps as text files

## Data Inputs

Required inputs:

- 3DVA dataset root with meshes and GT:
  `VISUAL_ATTENTION_3D_SHAPES_ROOT`
- canonical object placement JSONs:
  `THREE_DVA_JSON_ROOT` or repository path
  `jsons/object_placement/3dva_jsons`
- processed participant fixation JSON root:
  `FIXATION_ROOT`, `REPROJECT_PROCESSED_FIXATIONS_ROOT`, or
  `THREE_DVA_PROCESSED_FIXATIONS_ROOT`
- combined GT directory:
  `THREE_DVA_COMBINED_GT_DIR`

Current rc4 server configuration uses:

- repo:
  `/mnt/ssd1/29d_kon/acm_2026/agents/coordinator/Mesh-Saliency-Projection`
- fixations:
  `${RELEASE_DATA_ROOT}/participant_fixations_offset0_full_cleaned`
- 3DVA dataset:
  `${RELEASE_DATA_ROOT}/datasets/3DVA`
- placement JSON:
  repository `jsons/object_placement/3dva_jsons`

## Ground Truth

3DVA has per-view fixation maps in the dataset. The current benchmark does not
compare separately to only one static view. Instead, it uses a combined GT built
from available views.

The combined GT file for a model is:

- `{combined_gt_dir}/{model}_combined_gt.txt`

The combined support mask is the union of source-view coverage and positive GT.
Summary metrics should use:

- `metrics_vs_gt_combined.<method>.metrics_covered_only`

This avoids penalizing predictions on vertices that were not meaningfully covered
by the source GT views.

`A380` has a known video/session override in the runner:

- `A380 -> video_id 2365`

## Geometry And Projection

The implemented 3DVA transform path in `eval_3dva_cone_combined.py` is:

1. load mesh from the 3DVA dataset;
2. optionally apply static `base_rotate_z`;
3. recenter using the original bounding-box center;
4. scale according to the placement/model settings;
5. apply per-frame animated `rotZ`;
6. apply optional extra runtime rotations;
7. translate to the JSON-defined model location;
8. project or raycast using the reconstructed camera/FOV.

The default projection FOV mode is:

- `horizontal_to_vertical`

This treats the JSON FOV as horizontal and converts it to the effective vertical
FOV for 16:9 rendering. This matches the corrected preview/alignment work.

## Implemented Methods

### `screen_space_gaussian`

Script:

- `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py`

High-level behavior:

1. aggregate participant fixation points in screen space;
2. build a blurred 2D gaze density map;
3. project mesh vertices into each frame;
4. sample the screen-space density at projected vertex positions;
5. accumulate values onto vertices;
6. compare the final per-vertex prediction to combined GT.

This method is primarily controlled by a screen blur parameter, currently exposed
as pixel/screen sigma depending on dataset-specific evaluator.

### `raycast_nearest_vertex`

Script:

- `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py`

High-level behavior:

1. for each gaze point and placement frame, construct a camera ray;
2. intersect the ray with the mesh;
3. assign the hit to the nearest vertex of the hit triangle;
4. accumulate a per-vertex map;
5. compare to combined GT.

This is a hard assignment baseline and is produced by the same evaluator as
`cone_gaussian_on_mesh`.

### `cone_gaussian_on_mesh`

Script:

- `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py`

High-level behavior:

1. cast the gaze ray and find the mesh hit;
2. convert angular uncertainty to a world-space Gaussian scale near the hit;
3. query vertices around the hit within `radius_sigma_mult * sigma_world`;
4. distribute contribution with a Gaussian kernel;
5. accumulate a per-vertex map;
6. compare to combined GT.

Main parameters:

- `--sigma-deg`: angular uncertainty of the gaze ray in degrees;
- `--radius-sigma-mult`: finite support radius multiplier for the Gaussian.

`raycast` and `cone` are produced by the same heavy script. In batch mode they
can appear at the end of a run because they are slower than screen-space sampling
and because both methods rely on ray-mesh intersection.

## Metrics And Normalization

Prediction and GT arrays are normalized inside the metric functions as required
by each metric family. Reports and CSVs include metrics such as:

- `CC`
- `SIM`
- `KLD`
- `MSE`
- `MAE`
- `Spearman`
- `Cosine`
- proxy `AUC_Judd` and `NSS` at GT top-percentile thresholds

For summary tables, use the covered-only metric block:

- `metrics_vs_gt_combined.<method>.metrics_covered_only`

Do not mix full-vertex metrics and covered-only metrics in the same benchmark
table.

## Smoke Status

Historical rc2 smoke evidence:

- run id: `rc2_smoke_20260610_122103`
- output:
  `/mnt/ssd1/29d_kon/acm_2026/outputs/coordinator/rc2_smoke_20260610_122103`
- 3DVA tasks: 4/4 ok
- tested models: `bunny`, `A380`
- tested methods: `screen_space`, `cone`
- all reports used the superseded `fixation_format == "cropped_reset_offset_2000"`

This smoke validates the current 3DVA path sufficiently to start a larger run,
provided the same historical rc2 fixation root and matching repository revision
are used. These reports must not be resumed as rc4 baseline runs.

## Operational Notes

- Use `--no-resume` when changing fixation format, GT, sigma parameters, or
  transform settings.
- Use low process priority on shared servers: `--nice-level 15` or similar.
- Cone/raycast are CPU-bound and much slower than screen-space sampling.
- GPU is not required for these metric evaluators; rendering tasks are separate.
- Keep result folders tagged by date/run id to avoid mixing old CSV-compat runs
  with historical rc2 processed JSON runs.

# Mesh-Saliency-Projection

Core benchmark code for projecting screen-space participant fixations onto 3D
meshes and evaluating predicted saliency against dataset ground truth.

## Current Contract

- Release target: `v2.0-data-rc4`, schema version `2`.
- Canonical gaze input: 298 tracked offset0 fixation JSON files under
  `participant_data/processed_fixations_offset0_full_cleaned/`.
- Timing: `one_turn_from_start`, `gaze[k] -> placement[k]`, no default delay.
- Evaluation window: first 450 frames for 3DVA/MeshMamba and first 660 for
  SAL3D; the final 60 frames are excluded.
- Primary methods: `screen_space_gaussian` and `cone_gaussian_on_mesh`.
- SAL3D evaluation: repaired meshes plus fixed per-face GT.
- Portable result tables: `results/csv/manifest.csv`.

The authoritative run parameters and CSV schema are in
[docs/METRIC_RUN_AND_CSV_CONTRACT.md](./docs/METRIC_RUN_AND_CSV_CONTRACT.md).

## Core Layout

| Path | Responsibility |
| --- | --- |
| `metrics/` | Trusted metric implementations |
| `reprojection_methods/` | Projection evaluators |
| `utils/` | Shared loading, timing, provenance, and GT helpers |
| `test/launch/` | Reference, sweep, ablation, merge, and full-run launchers |
| `scripts/` | Release and data-contract lifecycle |
| `configs/`, `server/` | Reproducible local/server configuration |
| `jsons/` | Canonical object-placement and model metadata |
| `participant_data/` | Canonical tracked processed fixation JSON |
| `results/csv/` | Deduplicated portable CSV results and manifest |

Auxiliary alignment, heatmap, and video tools are still present during final
integration. Their planned public-submodule boundary is documented in
[docs/CORE_TOOLS_BOUNDARY.md](./docs/CORE_TOOLS_BOUNDARY.md). The core benchmark
must remain usable without those tools.

## Quick Start

```bash
python3 -m pytest -q

python3 test/launch/run_meshmamba_reference_batch.py \
  --methods screen_space cone \
  --texture-types non_texture \
  --models Starfruit_L3 Pear_L3 \
  --fixation-root participant_data/processed_fixations_offset0_full_cleaned \
  --batch-output-dir results/quick_meshmamba_smoke \
  --no-resume
```

Never resume a run after changing release, fixation data, timing, GT, or sigma
configuration unless the launcher confirms the stored provenance is compatible.

## Release Lifecycle

Large meshes, GT, original participant CSV, SAL3D Smooth Gaze, and source videos
remain external and are distributed through GitHub Releases. The processed
offset0 fixation JSON is also tracked in Git so its exact benchmark input is
reviewable.

```bash
python3 scripts/validate_data_contract.py \
  --csv-root /path/to/GAZE_DATA/csv_for_models \
  --processed-root participant_data/processed_fixations_offset0_full_cleaned \
  --timing-contract one_turn_from_start \
  --allow-known-blockers

python3 scripts/build_release_candidate.py --dry-run \
  --participant-csv-source /path/to/GAZE_DATA/csv_for_models

python3 scripts/validate_release_candidate.py release_assets/v2.0-data-rc4
```

The complete release contract is in
[docs/RELEASE_BUILD_AND_VALIDATION.md](./docs/RELEASE_BUILD_AND_VALIDATION.md).
SAL3D Smooth Gaze size, inventory mismatch, and usage are explained in
[docs/SMOOTH_GAZE_AND_FIXED_FACE_GT.md](./docs/SMOOTH_GAZE_AND_FIXED_FACE_GT.md).

## Documentation

- [docs/README.md](./docs/README.md): documentation index.
- [docs/FINAL_INTEGRATION_HISTORY.md](./docs/FINAL_INTEGRATION_HISTORY.md):
  contract history and integration decisions.
- [coordination/DATA_CONTRACT.md](./coordination/DATA_CONTRACT.md): canonical
  input and timing contract.
- [results/csv/README.md](./results/csv/README.md): portable result categories.
- [coordination/reviews/FINAL_INTEGRATION_AUDIT.md](./coordination/reviews/FINAL_INTEGRATION_AUDIT.md):
  final acceptance gates and known remaining work.

Historical `rc1`, `rc2`, and legacy timing/data paths may remain in archived
documents or result categories. They are not the current benchmark contract.

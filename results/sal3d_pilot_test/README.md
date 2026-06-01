# results/sal3d_pilot_test/

Pilot run of SAL3D evaluation (3 models: A380, bunny, lion).
Used to validate the eval pipeline before running all 57 models.

## Models tested

- `A380`, `bunny`, `lion`

## Methods

| Method | Output subdir |
|--------|--------------|
| cone_gaussian_on_mesh | `baseline_cone/` |
| screen_space_gaussian v1 | `baseline_screen_space/` |

## Summary CSVs

| File | Contents |
|------|----------|
| `sal3d_reference_long.csv` | One row per model-metric |
| `sal3d_reference_summary.csv` | Mean across models |
| `sal3d_reference_wide.csv` | One row per model, metrics as columns |

## Note on metrics validity

These results use `metrics_vs_gt_full_mesh`. For correct comparison use
`metrics_vs_gt_covered_only` from the individual `*_report.json` files —
see `datasets/README.md` for the GT coverage issue explanation.

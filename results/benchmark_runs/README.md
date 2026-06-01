# results/benchmark_runs/

Full benchmark run outputs. Each subfolder = one completed run.

## Naming convention

```
<date>_<texture_type>_<method>/
  meshmamba_reference_long.csv     one row per model-metric
  meshmamba_reference_summary.csv  one row per metric (mean across models)
  meshmamba_reference_wide.csv     one row per model, metrics as columns
  README.md                        run parameters and recipe
```

## Current runs (MeshMamba, 105 models each)

| Run | Track | Method | CC mean | CC (excl. CC<0) |
|-----|-------|--------|---------|-----------------|
| [2026-06-01_non_texture_cone](./meshmamba/2026-06-01_non_texture_cone/) | non_texture | cone_gaussian_on_mesh | 0.321 | 0.372 |
| [2026-06-01_non_texture_screen_space](./meshmamba/2026-06-01_non_texture_screen_space/) | non_texture | screen_space_gaussian v1 | 0.136 | 0.218 |
| [2026-06-01_rgb_texture_cone](./meshmamba/2026-06-01_rgb_texture_cone/) | rgb_texture | cone_gaussian_on_mesh | 0.274 | 0.343 |
| [2026-06-01_rgb_texture_screen_space](./meshmamba/2026-06-01_rgb_texture_screen_space/) | rgb_texture | screen_space_gaussian v1 | 0.130 | 0.219 |

Note: screen_space results use v1 (sigma=0.05×256px = 96px equivalent).
v2 (sigma=26.3px at 1920px) is in development — see `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space_v2.py`.

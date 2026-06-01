# MeshMamba / non_texture / cone_gaussian_on_mesh — 2026-06-01

## Track

- texture_type: `non_texture`
- method: `cone_gaussian_on_mesh`

## Recipe

- `sigma_deg = 1.0`
- `radius_sigma_mult = 3.0`
- `recenter_to_bbox_center = true`
- `extra_rotate_x_deg = 90`
- `projection_fov_mode = horizontal_to_vertical`
- `transform_order = blender_rig`
- tag: `recenter_rotx90p0_horizontaltovertical_blender_rig`

## Server output

`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_batch_20260601/MeshMamba_reference_non_texture_cone`

## Inventory

- n_total: 105
- n_ok: 105
- n_failed: 0

## Key means (105 models)

| Metric | Mean | Median |
|--------|------|--------|
| CC | 0.3212 | 0.3112 |
| SIM | 0.5935 | 0.5975 |
| KLD | 0.9635 | 0.6441 |
| MSE | 0.0532 | 0.0510 |
| Spearman | 0.2684 | 0.2802 |
| AUC_Judd_top10pct | 0.6936 | 0.7100 |
| NSS_top10pct | 0.7351 | 0.5845 |
| hit_rate | 0.8974 | 0.9066 |

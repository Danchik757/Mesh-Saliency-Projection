# MeshMamba / rgb_texture / cone_gaussian_on_mesh — 2026-06-01

## Track

- texture_type: `rgb_texture`
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

`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_batch_20260601/MeshMamba_reference_rgb_cone`

## Inventory

- n_total: 105
- n_ok: 104
- n_failed: 1

### Failed model

- `stuffed_animal_v1_L2` — `runtime_error`: "Expected a single Trimesh"
  (OBJ contains multiple sub-meshes; trimesh returns a Scene instead of Trimesh)

## Key means (104 ok models)

| Metric | Mean | Median |
|--------|------|--------|
| CC | 0.2737 | 0.2515 |
| SIM | 0.5749 | 0.6066 |
| KLD | 1.1424 | 0.6772 |
| MSE | 0.0499 | 0.0444 |
| Spearman | 0.2356 | 0.2197 |
| AUC_Judd_top10pct | 0.6569 | 0.6767 |
| NSS_top10pct | 0.5877 | 0.4503 |
| hit_rate | 0.9143 | 0.9257 |

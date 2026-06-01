# MeshMamba / rgb_texture / screen_space_gaussian — 2026-06-01

## Track

- texture_type: `rgb_texture`
- method: `screen_space_gaussian`

## Recipe

- `sigma_screen = 0.05`
- `recenter_to_bbox_center = true`
- `extra_rotate_x_deg = 90`
- `projection_fov_mode = horizontal_to_vertical`
- `transform_order = blender_rig`
- tag: `sigma0p05_recenter_rotx90p0_horizontaltovertical_blender_rig`

## Server output

`/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_batch_20260601/MeshMamba_reference_rgb_screen`

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
| CC | 0.1304 | 0.0971 |
| SIM | 0.5756 | 0.5958 |
| KLD | 1.9317 | 1.6145 |
| MSE | 0.0838 | 0.0750 |
| Spearman | 0.1287 | 0.1042 |
| AUC_Judd_top10pct | 0.5716 | 0.5611 |
| NSS_top10pct | 0.2475 | 0.1970 |

# MeshMamba Non-Texture Screen-Space Batch

- Date: `2026-06-01`
- Track: `MeshMamba / non_texture / screen_space`
- Runner: [run_meshmamba_reference_batch.py](/Users/admin/Documents/LAB/SALIENCY_code/%23meshes_2.0/GITHUB/Mesh-Saliency-Projection/test/launch/run_meshmamba_reference_batch.py)
- Server output root:
  `/home/29d_kon@lab.graphicon.ru/ssd1_link/projects/REPROJECTING/outputs_batch_20260601/MeshMamba_reference_non_texture_screen`

## Recipe

- `texture_type = non_texture`
- `method = screen_space`
- `workers = 4`
- `sigma_screen = 0.05`
- `recenter_to_bbox_center = true`
- `extra_rotate_x_deg = 90`
- `projection_fov_mode = horizontal_to_vertical`
- `transform_order = blender_rig`

## Outcome

- `n_total = 105`
- `n_ok = 105`
- `n_failed = 0`

Means:

- `CC_mean = 0.13591947623655978`
- `SIM_mean = 0.5832579657344064`
- `KLD_mean = 1.953946045574988`
- `MSE_mean = 0.08206105136241487`
- `Spearman_mean = 0.12720840586131796`
- `AUC_Judd_gt_top_10pct_proxy_mean = 0.5818559422576015`

Artifacts in this folder:

- `meshmamba_reference_long.csv`
- `meshmamba_reference_wide.csv`
- `meshmamba_reference_summary.csv`

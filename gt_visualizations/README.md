# gt_visualizations/

Canonical location for method-specific `prediction vs GT` preview scripts.

These scripts render diagnostic PNGs that let you inspect:
- where gaze landed on the screen
- what saliency map the method predicted on the mesh
- what GT saliency map we compare against in metrics

Each viewer produces:
- `<output-dir>/<model>__<method>__frame<NNNN>.png` — three-panel frame previews
- `<output-dir>/<model>__<method>__summary.png` — accumulated prediction vs GT

Panel order is always the same:
- left: gaze density
- middle: predicted saliency
- right: GT saliency

## Available viewers

### `preview_meshmamba_screenspace_alignment.py`

Dataset/method:
- MeshMamba
- `screen_space_gaussian`

Purpose:
- check for Y-flip / coordinate-system mistakes
- verify that face-centroid projections align with the gaze density
- inspect whether predicted hotspots match GT hotspots

Example:

```bash
source configs/server_vg_intellect.env
$REPROJECT_PYTHON gt_visualizations/preview_meshmamba_screenspace_alignment.py \
    --model Rubber_Duck_v1_L3 \
    --texture-type non_texture \
    --output-dir /tmp/preview_meshmamba_screen
```

### `preview_meshmamba_cone_alignment.py`

Dataset/method:
- MeshMamba
- `cone_gaussian_on_mesh`

Purpose:
- verify ray-hit + cone-spread behaviour visually
- inspect whether projected cone saliency lands on plausible face regions
- compare the accumulated cone map against GT

Example:

```bash
source test/env/local_paths.example.sh
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 \
    gt_visualizations/preview_meshmamba_cone_alignment.py \
    --model Starfruit_L3 \
    --texture-type non_texture \
    --output-dir /tmp/preview_meshmamba_cone
```

Quick smoke:

```bash
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 \
    gt_visualizations/preview_meshmamba_cone_alignment.py \
    --model Starfruit_L3 \
    --texture-type non_texture \
    --max-frames 12 \
    --output-dir /tmp/preview_meshmamba_cone_quick
```

### `preview_sal3d_screenspace_alignment.py`

Dataset/method:
- SAL3D
- `screen_space_gaussian`

Purpose:
- SAL3D-specific analogue of the MeshMamba screen-space viewer
- verify vertex projection, GT alignment and Smooth_Gaze handling

Example:

```bash
source test/env/local_paths.example.sh
python3 gt_visualizations/preview_sal3d_screenspace_alignment.py \
    --model bunny \
    --output-dir /tmp/preview_sal3d
```

## Batch diagnostic bundles

### `generate_meshmamba_worst_case_bundle.py`

Reads the MeshMamba benchmark CSV and builds two ranked diagnostic bundles:
- worst `KLD` cases
- worst `CC` cases

For each selected row it runs the correct viewer automatically:
- `cone` -> `preview_meshmamba_cone_alignment.py`
- `screen_space` -> `preview_meshmamba_screenspace_alignment.py`

Outputs:
- `generated/<texture>__<method>__<model>/...png`
- `worst_kld_top10/`
- `worst_cc_top10/`
- `worst_kld_top10.zip`
- `worst_cc_top10.zip`

Example:

```bash
source test/env/local_paths.example.sh
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 \
    gt_visualizations/generate_meshmamba_worst_case_bundle.py \
    --workers 4
```

Useful rerun mode after partial completion:

```bash
/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3 \
    gt_visualizations/generate_meshmamba_worst_case_bundle.py \
    --workers 1 \
    --skip-existing
```

## Notes

- These scripts are debug/inspection tools, not benchmark launchers.
- They intentionally mirror the transform/projection logic from the corresponding
  eval scripts so visual discrepancies can expose metric-pipeline bugs quickly.

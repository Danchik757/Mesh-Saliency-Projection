# test/tools/

Diagnostic and utility scripts for inspecting pipeline correctness.
These are helper tools, not the main benchmark runners.

Method-specific `prediction vs GT` viewers now live in:

```text
gt_visualizations/
```

See [../../gt_visualizations/README.md](../../gt_visualizations/README.md) for:
- MeshMamba `screen_space_gaussian`
- MeshMamba `cone_gaussian_on_mesh`
- SAL3D `screen_space_gaussian`

Thin compatibility wrappers are kept in `test/tools/` for the historical paths:
- `preview_screenspace_alignment.py`
- `preview_meshmamba_cone_alignment.py`
- `preview_sal3d_screenspace_alignment.py`

## Tools

### `render_preview_from_manifest.py` — alignment preview

Renders one frame of a manifest using the same trimesh projection code
as the eval scripts. Use to visually verify OBJ→screen alignment.

```bash
source test/env/local_paths.sh
python3 test/tools/render_preview_from_manifest.py \
    --manifest test/manifests/preview_meshmamba_non_texture_rubber_duck.json
```

Output: PNG overlay at `$REPROJECT_OUTPUT_ROOT/preview_checks/...`

### `export_metrics_csv.py` — batch JSON → CSV export

Reads all `*_report.json` outputs from an eval run and writes flat CSV rows
suitable for spreadsheets and analysis.

```bash
python3 test/tools/export_metrics_csv.py \
    --input-dir results/benchmark_runs/meshmamba/2026-06-01_non_texture_cone \
    --output results/benchmark_runs/meshmamba/2026-06-01_non_texture_cone/summary.csv
```

### `generate_sal3d_jsons.py` — SAL3D camera JSON generator

Generates `Sal3D_<model>.json` files for each SAL3D model, encoding the
Blender camera and animation params used during rendering.

```bash
python3 test/tools/generate_sal3d_jsons.py \
    --meshes-dir $REPROJECT_DATASET_SAL3D_ROOT/Meshes \
    --output-dir $REPROJECT_GAZE_JSON_SAL3D_ROOT
```

### `debug_single_gaze_projection.py` — single-frame projection debugger

Prints per-face projection details for one frame. Useful for tracing
why a specific frame contributes unexpectedly to the saliency map.

### `make_preview_overlay.py` — video + projection overlay

Creates a side-by-side video showing the source recording and the
projected saliency overlay on the mesh.

### `render_camera_distance_sweep.py` — camera distance sensitivity test

Renders one model at multiple camera distances to check projection stability.

# test/launch/

Shell and Python wrappers for running evaluations locally or on vg-intellect.
All scripts read paths from env vars — source the appropriate env file first.

```bash
source test/env/local_paths.sh          # local machine
source configs/server_vg_intellect.env  # on vg-intellect
```

## Reference batch runners (canonical, full 105/32/57 models)

| Script | Dataset | Description |
|--------|---------|-------------|
| `run_meshmamba_reference_batch.py` | MeshMamba | Runs all 105 models, both tracks, both methods. Writes to `results/benchmark_runs/meshmamba/`. |
| `run_sal3d_reference_batch.py` | SAL3D | Runs all SAL3D models. Writes to `results/benchmark_runs/sal3d/`. |

```bash
# Full MeshMamba benchmark (server, takes hours):
$REPROJECT_PYTHON test/launch/run_meshmamba_reference_batch.py \
    --texture-types non_texture rgb_texture \
    --methods cone screen_space \
    --workers 4

# SAL3D full batch:
$REPROJECT_PYTHON test/launch/run_sal3d_reference_batch.py --workers 4
```

## Pilot launchers (single model or small subset)

| Script | Dataset | Notes |
|--------|---------|-------|
| `run_meshmamba_non_texture_pilot.sh` | MeshMamba | Non-texture track, a few models |
| `run_meshmamba_baseline_cone.sh` | MeshMamba | Cone method, non-texture |
| `run_meshmamba_baseline_screen_space.sh` | MeshMamba | Screen-space method, non-texture |
| `run_3dva_pilot.sh` | 3DVA | Small subset, published-dataset eval style |
| `run_3dva_raycast_cone.sh` | 3DVA | Raycast + cone, uses our gaze CSV |
| `run_3dva_screen_space.sh` | 3DVA | Screen-space, uses our gaze CSV |
| `run_sal3d_cone.sh` | SAL3D | Cone method batch launcher |
| `run_saliency3d_clear_pilot.sh` | Saliency3D_clear | Separate dataset (not SAL3D) |

## Alignment and preview

| Script | What it does |
|--------|-------------|
| `run_preview_manifest.sh` | Renders one manifest through the Python trimesh previewer |
| `run_preview_suite.sh` | Renders a batch of manifests |
| `run_metric_preflight.sh` | Sanity checks env vars and data paths before running metrics |

```bash
bash test/launch/run_preview_manifest.sh \
    test/manifests/preview_meshmamba_non_texture_rubber_duck.json
```

## Server transfer

| Script | What it does |
|--------|-------------|
| `mirror_side_inputs.sh` | Packs gaze CSVs + camera JSONs locally and scps them to vg-intellect |

See `test/side_inputs/README.md` for the full transfer workflow.

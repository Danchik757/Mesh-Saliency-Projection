# Mesh-Saliency-Projection

Repository for the main codebase of the mesh saliency projection project.
Implements multiple methods for transferring screen-space gaze data onto 3D mesh vertices/faces
and evaluating the result against ground-truth saliency maps.

## Current focus

- Benchmark pipeline for 3DVA and MeshMamba datasets (all 32+16 models);
- Cone projection + raycast nearest-vertex method (primary);
- Screen-space Gaussian baseline;
- Geodesic diffusion method;
- Shared metric suite: CC, KL, NSS, AUC-Judd, Similarity.

## Datasets validated

| Dataset | Models | Mean IoU | Status |
|---------|--------|----------|--------|
| MeshMamba non_texture | 8 | ≥ 0.987 | ✅ validated |
| MeshMamba rgb_texture | 8 | ≥ 0.990 | ✅ validated |
| 3DVA | 32 | 0.946 | ✅ validated |
| SAL3D | TBD | — | in progress |

Alignment validation details: [test/README.md](./test/README.md)

## Repository structure

| Folder | Contents |
|--------|----------|
| [metrics/](./metrics/README.md) | Shared metric implementations (CC, KL, NSS, AUC, Similarity) |
| [reprojection_methods/](./reprojection_methods/README.md) | All projection methods (cone, screen-space, geodesic) |
| [test/](./test/README.md) | Alignment validation: scripts, manifests, Blender canonical check |
| [test/launch/](./test/launch/README.md) | Batch and pilot eval launchers for all datasets |
| [test/manifests/](./test/manifests/README.md) | Per-model alignment check manifests (validated IoU) |
| [test/tools/](./test/tools/README.md) | Diagnostic and preview utilities (no eval, debug only) |
| [datasets/](./datasets/README.md) | Dataset reference: contents, sizes, formats, validation status |
| [scripts/](./scripts/README.md) | Dataset download/upload scripts and method comparison tools |
| [docs/](./docs/EVAL_RUNBOOK.md) | Eval runbook and project architecture notes |
| [video_creation/](./video_creation/README.md) | Scripts for generating render videos |
| [requirements/](./requirements/README.md) | Per-environment dependency lists |
| [PIPELINE.md](./PIPELINE.md) | Benchmark pipeline design options |
| [DATA_PATHS.md](./DATA_PATHS.md) | Reference: all local and server file paths |

## Getting the datasets

Datasets are distributed as ZIP archives attached to a GitHub release.
On a new machine:

```bash
# 1. Download and extract all core data (~1.8 GB without videos)
bash scripts/download_datasets.sh --data-root /path/to/data

# 2. Configure env vars
cp test/env/new_machine.env.sh.template test/env/local_paths.sh
# edit DATA_ROOT in local_paths.sh
source test/env/local_paths.sh
```

Optional flags for `download_datasets.sh`:

| Flag | What it adds |
|------|-------------|
| `--with-smooth-gaze` | SAL3D smooth-gaze neighbour lists (~2 GB, auxiliary only) |
| `--with-videos` | Rendered videos for all datasets (~256 MB, needed for alignment check) |
| `--only PATTERN` | Download only matching ZIPs (e.g. `--only "3dva*"`) |
| `--list` | Print all available release assets and exit |

To create a new release from local data (maintainer only):
```bash
bash scripts/package_datasets.sh          # creates release_assets/*.zip
bash scripts/upload_release.sh            # uploads to GitHub release v1.0-data
```

---

## Visual verification of screen_space method

Before relying on metrics, run the visual sanity check to confirm the method
projects gaze to the correct mesh faces (no coordinate-system or Y-flip bugs):

```bash
# On vg-intellect:
source configs/server_vg_intellect.env
$REPROJECT_PYTHON test/tools/preview_screenspace_alignment.py \
    --model Rubber_Duck_v1_L3 \
    --texture-type non_texture \
    --output-dir /tmp/preview_v2
```

Output: three-panel PNG images per frame.

| Panel | What it shows |
|-------|--------------|
| **Left** — Gaze density | Where participants looked on screen (input to the method) |
| **Middle** — Predicted saliency | **Our result**: per-face salience assigned by screen_space |
| **Right** — GT saliency | Ground-truth per-face CSV from the dataset (reference) |

Check that hot spots in **Middle** spatially match hot spots in **Right**.
Script: [`test/tools/preview_screenspace_alignment.py`](./test/tools/preview_screenspace_alignment.py)

## Quick start

```bash
# Set up local environment variables
source test/env/local_paths.example.sh

# Run 3DVA eval for one model
python3 reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py \
    --model bunny \
    --dataset-root "$REPROJECT_DATASET_3DVA_ROOT" \
    --csv-root     "$REPROJECT_GAZE_CSV_3DVA_ROOT" \
    --json-root    "$REPROJECT_GAZE_JSON_3DVA_ROOT" \
    --recenter-to-bbox-center \
    --output-dir   results/3dva/cone_gaussian/bunny

# Run MeshMamba eval for one model
python3 reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py \
    --model Penguin \
    --texture-type non_texture \
    --dataset-root "$REPROJECT_DATASET_MESHMAMBA_ROOT" \
    --csv-root     "$REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT" \
    --json-root    "$REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT" \
    --output-dir   results/meshmamba/non_texture/cone_gaussian/Penguin
```

## Data paths

All local and server paths are documented in [DATA_PATHS.md](./DATA_PATHS.md).

Raw datasets stay **outside** the repository. Generated outputs go into `results/`.

Reference:
- [Google Sheets dataset table](https://docs.google.com/spreadsheets/d/1UpTHzfqAma46_czqMvlA_15AVIm5T2Em6d_BmskiCkQ/edit?gid=881515507#gid=881515507)

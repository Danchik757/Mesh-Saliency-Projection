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
| [test/](./test/README.md) | Alignment validation scripts and manifests |
| [datasets/](./datasets/README.md) | Dataset-level metadata |
| [video_creation/](./video_creation/README.md) | Scripts for generating render videos |
| [requirements/](./requirements/README.md) | Per-environment dependency lists |
| [docs/](./docs/project_structure.md) | Project structure and architecture notes |
| [PIPELINE.md](./PIPELINE.md) | Benchmark pipeline design options |
| [DATA_PATHS.md](./DATA_PATHS.md) | Reference: all local and server file paths |

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

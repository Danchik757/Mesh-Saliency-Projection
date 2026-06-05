# Canonical Camera JSONs

This directory is the repository-local source of truth for camera, projection,
scale, and animation JSONs used by gaze reprojection benchmarks.

Do not use `GAZE_DATA/jsons_for_models` or dataset release JSONs for benchmark
runs unless the goal is an explicit diagnostic comparison. In particular,
SAL3D release JSONs differ from the corrected render-export JSONs stored here.

## Layout

| Directory | Dataset/track | Count | Filename prefix |
| --- | --- | ---: | --- |
| `3dva_jsons/` | 3DVA | 32 | `3DVA_` |
| `mamba_non_jsons/` | MeshMamba non_texture | 105 | `MeshMamba_non_texture_` |
| `mamba_rgb_jsons/` | MeshMamba rgb_texture | 105 | `MeshMamba_rgb_texture_` |
| `sal3d_jsons/` | SAL3D | 57 | `Sal3D_` |

Total: 299 JSON files.

## Required Usage

Server and local environment files should point JSON roots here:

```bash
export REPROJECT_CANONICAL_JSON_ROOT="${REPO_ROOT}/jsons"
export THREE_DVA_JSON_ROOT="${REPROJECT_CANONICAL_JSON_ROOT}/3dva_jsons"
export MESHMAMBA_JSON_ROOT="${REPROJECT_CANONICAL_JSON_ROOT}/mamba_non_jsons"
export MESHMAMBA_RGB_TEXTURE_JSON_ROOT="${REPROJECT_CANONICAL_JSON_ROOT}/mamba_rgb_jsons"
export SAL3D_JSON_ROOT="${REPROJECT_CANONICAL_JSON_ROOT}/sal3d_jsons"
```

CSV gaze files and dataset meshes/GT still live outside the repository.

## Validation

Run this before launching new metric batches:

```bash
python3 test/tools/validate_canonical_jsons.py
```

Expected result:

```text
VALIDATED_JSON_FILES 299
ERRORS 0
WARNINGS 0
```

The validator checks JSON syntax, required camera/model/video/animation fields,
4x4 view/projection matrices, positive scales and bounding dimensions, frame
count, monotonic timestamps, and radians/degrees consistency for per-frame
object rotation.

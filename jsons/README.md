# Canonical Camera JSONs

This directory is the repository-local source of truth for camera, projection,
scale, animation, and model/dataset index JSONs used by gaze reprojection
benchmarks.

Do not use `GAZE_DATA/jsons_for_models` or dataset release JSONs for benchmark
runs unless the goal is an explicit diagnostic comparison. In particular,
SAL3D release JSONs differ from the corrected render-export JSONs stored here.

## Layout

| Directory | Purpose |
| --- | --- |
| `object_placement/` | Full camera/object/render JSONs used directly by projection code. |
| `dataset_model_info/` | Generated per-dataset model indexes and data-source manifests. |

`object_placement/` contains:

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
export REPROJECT_OBJECT_PLACEMENT_JSON_ROOT="${REPO_ROOT}/jsons/object_placement"
export THREE_DVA_JSON_ROOT="${REPROJECT_OBJECT_PLACEMENT_JSON_ROOT}/3dva_jsons"
export MESHMAMBA_JSON_ROOT="${REPROJECT_OBJECT_PLACEMENT_JSON_ROOT}/mamba_non_jsons"
export MESHMAMBA_RGB_TEXTURE_JSON_ROOT="${REPROJECT_OBJECT_PLACEMENT_JSON_ROOT}/mamba_rgb_jsons"
export SAL3D_JSON_ROOT="${REPROJECT_OBJECT_PLACEMENT_JSON_ROOT}/sal3d_jsons"
```

Old participant CSVs and new processed fixation JSONs are staged under
`participant_data/`. They are separate from the placement JSONs in this
directory. Large data payloads are distributed through versioned GitHub Release
assets.

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

Regenerate dataset/model indexes after changing `object_placement/`:

```bash
python3 test/tools/generate_dataset_model_info.py
```

The participant gaze observations are not stored here as JSON. They are stored
under `participant_data/`:

- `collected_gaze_csv_by_model/` contains the old participant CSV format;
- `processed_fixations_offset0_full_cleaned/` contains the canonical full-length
  frame-wise gaze JSON used by current benchmark evaluators.

See `coordination/DATA_CONTRACT.md` before changing input or timing logic.

# Eval Runbook — Correct Evaluation Pipeline
Last updated: 2026-06-09

This document describes the **correct** way to run gaze-to-mesh saliency evaluation
for all three datasets. Read this before running any eval on the server.

> **Current migration gate:** commands below describe the validated geometry/FOV
> baseline, but existing evaluators still consume original participant CSVs.
> They are diagnostic-only until the shared processed-fixation loader and the
> approved `processed[k] -> placement[round(1.8*fps)+k]` timing rule are
> integrated. Do not start final full benchmarks from these commands yet.

---

## Quick-start summary

| Dataset | Script | Key flags | GT type |
|---|---|---|---|
| MeshMamba non_texture | `eval_meshmamba_cone.py` | `--texture-type non_texture --recenter-to-bbox-center --projection-fov-mode horizontal_to_vertical --transform-order blender_rig --extra-rotate-x-deg 90` | per-face CSV |
| MeshMamba rgb_texture | same | `--texture-type rgb_texture` + different `--csv-root --json-root` | per-face CSV |
| 3DVA | `eval_3dva_raycast_cone.py` | `--recenter-to-bbox-center --projection-fov-mode horizontal_to_vertical` + optional `--video-id` | per-vertex TXT (3 views) |
| SAL3D | `eval_sal3d_cone.py` | defaults already correct | per-vertex from Gaze/*.txt col.6 |

---

## Dataset 1: MeshMamba non_texture

### Data paths (local)
```
OBJ:   GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/non_texture/<model>/
GT:    GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/non_texture/<model>.csv
CSV:   GAZE_DATA/csv_for_models/MeshMamba_non_texture/<model>.csv
JSON:  jsons/object_placement/mamba_non_jsons/MeshMamba_non_texture_<model>.json
```

### Correct command
```bash
VENV="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3"
REPO="/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection"

"$VENV" "$REPO/reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py" \
    --model Rubber_Duck_v1_L3 \
    --texture-type non_texture \
    --dataset-root "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency" \
    --csv-root "GAZE_DATA/csv_for_models/MeshMamba_non_texture" \
    --json-root "$REPO/jsons/object_placement/mamba_non_jsons" \
    --output-dir "/tmp/results_mamba" \
    --recenter-to-bbox-center \
    --extra-rotate-x-deg 90.0 \
    --projection-fov-mode horizontal_to_vertical \
    --transform-order blender_rig
```

### Why these flags
- `--projection-fov-mode horizontal_to_vertical` — JSON stores 60° HORIZONTAL FOV,
  this flag converts it correctly to vertical 35.98°. WITHOUT this flag the projection
  matrix is wrong (rays miss by up to 10°), CC drops from ~0.60 to ~0.06.
- `--transform-order blender_rig` — replicates the Blender animation rig where local
  object rotations (extra_rotate_x) happen before the per-frame Z animation rotation.
  Validated with Blender canonical preview: IoU ≥ 0.987 for all 8 pilot models.
- `--extra-rotate-x-deg 90.0` — replicates the implicit OBJ import rotation from
  Blender's default axes (Y-up import tilts the model 90°).

### Screen-space variant
Same flags, use `eval_meshmamba_screen_space.py` with `--sigma-screen 0.05`.
Screen-space now uses the same authoritative transform/FOV defaults and performs
back-face culling against the camera direction. It is still a weaker method than
cone-on-mesh on many models, but no longer mixes obvious reverse-facing faces.

### Pilot models with validated geometry (IoU ≥ 0.987)
Starfruit_L3, Mango_L3, Pear_L3, Rubber_Duck_v1_L3,
Penguin_V2_L3, Moai_v3_L3, SeaHorse_v2_L3, Rhinoceros_v1_L3

### GT / OBJ naming mismatches
- Resolver now falls back through the actual OBJ stem when matching GT.
- This explicitly covers cases such as:
  - Penguin_V2_L3 → Penguin_v1_iterations-2.csv
  - Moai_v3_L3 → Moai_L3.csv
  - SeaHorse_v2_L3 → SeaHorse_v1_iterations-2.csv
- 4 models have NO GT: Eagle_wood, PoloTeamShirt, White-TailedDeer, barbiegirl

---

## Dataset 2: MeshMamba rgb_texture

### Data paths (local)
```
OBJ:   GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/rgb_texture/<model>/
GT:    GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/rgb_texture/<model>.csv
CSV:   GAZE_DATA/csv_for_models/MeshMamba_rgb_texture/<model>.csv
JSON:  jsons/object_placement/mamba_rgb_jsons/MeshMamba_rgb_texture_<model>.json
```

### Correct command
```bash
"$VENV" "$REPO/reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py" \
    --model Rubber_Duck_v1_L3 \
    --texture-type rgb_texture \                # ← KEY DIFFERENCE
    --dataset-root "GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency" \
    --csv-root "GAZE_DATA/csv_for_models/MeshMamba_rgb_texture" \       # ← different CSV dir
    --json-root "$REPO/jsons/object_placement/mamba_rgb_jsons" \        # ← different JSON dir
    --output-dir "/tmp/results_mamba_rgb" \
    --recenter-to-bbox-center \
    --extra-rotate-x-deg 90.0 \
    --projection-fov-mode horizontal_to_vertical \
    --transform-order blender_rig
```

### Important
- rgb_texture GT is DIFFERENT from non_texture GT (different participants, different saliency)
- rgb_texture CSV is also DIFFERENT (different participants watched different video)
- Same camera parameters (same JSON structure, same flags)

---

## Dataset 3: 3DVA

### Data paths (local)
```
OBJ:   GAZE_DATA/datasets/3DVA/3DModels-Simplif-up/<model>.obj   ← MUST use -up version
GT:    GAZE_DATA/datasets/3DVA/FixationMaps/<model>_300norm.txt   (+ 413, 599)
CSV:   GAZE_DATA/csv_for_models/3DVA/<model>.csv
JSON:  jsons/object_placement/3dva_jsons/3DVA_<model>.json
```

### Correct command
```bash
"$VENV" "$REPO/reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py" \
    --model bunny \
    --dataset-root "GAZE_DATA/datasets/3DVA" \
    --csv-root "GAZE_DATA/csv_for_models/3DVA" \
    --json-root "$REPO/jsons/object_placement/3dva_jsons" \
    --output-dir "/tmp/results_3dva" \
    --recenter-to-bbox-center \
    --projection-fov-mode horizontal_to_vertical
```

### Why horizontal_to_vertical for 3DVA
The current 3DVA evaluators support the same FOV resolution modes as the other
datasets. The recommended mode is:

```text
--projection-fov-mode horizontal_to_vertical
```

This treats the JSON `fov_degrees ≈ 60` as a horizontal FOV and converts it to
the effective vertical FOV for the current aspect ratio:

```text
h2v(60°, 16:9) = 35.9834°
```

`--override-fov-deg 35.9834 --projection-fov-mode vertical` remains valid for
diagnostics, but new batch runs should use the explicit `horizontal_to_vertical`
path because that is what the current launchers and reference batch runner use.

### CRITICAL: OBJ version
Always use 3DModels-Simplif-up/ (pre-rotated by render script).
NEVER use 3DModels-Simplif/ (wrong orientation → IoU drops from 0.978 to 0.72).
The dataset_root path should be the parent containing both 3DModels-Simplif-up/ and FixationMaps/.

### Understanding the three GT files (300, 413, 599)
These are THREE DIFFERENT STATIC VIEWPOINTS from the original 3DVA paper benchmark.
GT was collected from 20 observers looking at STATIC renderings of each model from
3 manually chosen camera positions. The numbers are viewpoint identifiers.

OUR data: from rotating videos → view-integrated gaze.
GT: from static images → view-specific gaze.
This mismatch is expected and all three GT variants should be reported.

### Authoritative geometry policy
Use:
- `recenter=True`
- `extra_rotate_x=0°`
- `projection_fov_mode=horizontal_to_vertical`

Reason:
- JSON exports contain `fov_degrees ≈ 60` and `projection_matrix[1,1] ≈ 1.732`, which means
  the stored matrix is using **vertical 60°**.
- On 16:9, that implies **horizontal ≈ 122.55°**, which is not the intended render setup.
- Therefore eval must reinterpret the JSON FOV as **horizontal 60°** and convert it
  to the correct effective vertical FOV, namely `35.9834°`.

NOTE: 3DVA render script uses forward='X', up='Z' → no extra rotation needed with -up OBJ.

### A380 special case
A380 CSV has TWO video_ids `[1970, 2365]` — data from two different sessions mixed.
The eval scripts now support `--video-id` for clean session filtering. If omitted,
they still process all rows, but the report records the mixed `video_ids_present`.

---

## Dataset 4: SAL3D

### Data paths (local)
```
OBJ:   GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Meshes/<model>.obj
GT:    GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Gaze/<model>.txt  (col 6 = smooth_saliency)
CSV:   GAZE_DATA/csv_for_models/SAL3D/<model>.csv
JSON:  jsons/object_placement/sal3d_jsons/Sal3D_<model>.json
```

### Correct command
```bash
"$VENV" "$REPO/reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py" \
    --model bunny \
    --dataset-root "GAZE_DATA/datasets/SAL3D/SAL3D_Dataset" \
    --csv-root "GAZE_DATA/csv_for_models/SAL3D" \
    --json-root "$REPO/jsons/object_placement/sal3d_jsons" \
    --output-dir "/tmp/results_sal3d"
    # All other flags are correct by default: h2v, blender_rig, recenter, rotX=90°
```

### SAL3D-specific issues

1. **20K vertex problem**: SAL3D GT was computed on 20K isotropic pointcloud.
   - 23 models: OBJ = 20K vertices → direct match, full GT coverage
   - 35 models: OBJ > 20K vertices → Gaze 20K is exact subset of OBJ vertices (dist=0)
     → unmatched OBJ vertices get GT=0 → CC is artificially lower for these models
   - FUTURE FIX: mask zero-GT vertices before computing CC for high-res models

2. **No view_matrix in JSON**: SAL3D JSONs lack view_matrix field.
   The script reconstructs it from rotation_euler_radians + location.

3. **GT format**: Gaze/<model>.txt columns:
   - 0-2: xyz vertex coordinates (20K points, subset of OBJ)
   - 3-5: vertex normals
   - 6: smooth saliency (use this as GT)
   - 7: binary saliency (1000 fixation points)

4. **Geometry validation**: IoU verified for 5 models (mean 0.958, min 0.907).
   JSONs are generated from sal_render_1.py parameters and are correct.

### Models with matching OBJ=20K (safe for eval)
bunny, dragon, octopus, camel, cow, cat... (23 total)
Check with: `python3 -c "import numpy as np,trimesh; m=trimesh.load('Meshes/X.obj',process=False); g=np.loadtxt('Gaze/X.txt'); print(len(m.vertices)==len(g))"`

---

## Parallel run template (4 models)

```bash
VENV="/path/to/venv/bin/python3"
SCRIPT="path/to/eval_meshmamba_cone.py"
OUT="/tmp/results"
mkdir -p "$OUT"

for MODEL in Rubber_Duck_v1_L3 Mango_L3 Rhinoceros_v1_L3 Starfruit_L3; do
    "$VENV" "$SCRIPT" \
        --model "$MODEL" \
        --texture-type non_texture \
        --dataset-root "$DATASET" \
        --csv-root "$CSV_ROOT" \
        --json-root "$JSON_ROOT" \
        --output-dir "$OUT" \
        --recenter-to-bbox-center \
        --extra-rotate-x-deg 90.0 \
        --projection-fov-mode horizontal_to_vertical \
        --transform-order blender_rig \
        > "$OUT/${MODEL}.log" 2>&1 &
done
wait && echo "All done"
```

---

## Common mistakes and fixes

| Mistake | Symptom | Fix |
|---|---|---|
| Missing `--projection-fov-mode h2v` | CC~0, KLD>8, hit_rate~0.22 | Add `--projection-fov-mode horizontal_to_vertical` |
| Using 3DModels-Simplif instead of -up | IoU~0.72, wrong geometry | Use `3DModels-Simplif-up/` |
| Wrong `--texture-type` | FileNotFoundError on JSON | Match texture_type to the csv/json directory |
| SAL3D OBJ≠20K | CC lower than expected | Normal — GT only covers 20K vertices |
| Penguin GT not found | FileNotFoundError | GT name = Penguin_v1_iterations-2.csv, use workaround |

---

## Server paths (vg-intellect)

```
Allowed root: /mnt/ssd1/29d_kon/acm_2026
Repo:         /mnt/ssd1/29d_kon/acm_2026/agents/<workspace>/Mesh-Saliency-Projection
Env:          /mnt/ssd1/29d_kon/acm_2026/environments/reproject-benchmark/bin/python
Release data: /mnt/ssd1/29d_kon/acm_2026/shared_release_data/v2.0-data-rc1/extracted
Outputs:      /mnt/ssd1/29d_kon/acm_2026/outputs/<workspace>
```

Before server run: push commits to GitHub, then on server:
```bash
cd /mnt/ssd1/29d_kon/acm_2026/agents/<workspace>/Mesh-Saliency-Projection
git fetch origin
source configs/server_vg_intellect.env
```

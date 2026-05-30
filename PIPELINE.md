# Benchmark Pipeline Design

This document describes options for a general configurable benchmark pipeline
and recommends a concrete approach.

---

## Current situation

Each eval script (`eval_3dva_raycast_cone.py`, `eval_meshmamba_cone.py`, etc.)
is self-contained and handles one dataset × method combination.
To run on a new model or with different parameters you edit CLI flags.

**Problem:** hard to reproduce, scale to 32 models, or compare methods systematically.

---

## What the pipeline must do

1. Load OBJ → apply axis remap (`forward=X, up=Z`) → recenter → scale from JSON
2. Load gaze CSV + camera JSON → per-frame gaze batches
3. Project gaze onto mesh (choose method)
4. Load GT (per-vertex or per-face values)
5. Compute metrics (CC, KL, NSS, AUC, ...)
6. Save result to a structured output directory

---

## Option A — YAML config + single runner (RECOMMENDED)

```
run_benchmark.py --config configs/3dva_cone.yaml [--model bunny]
```

**Config file** (`configs/3dva_cone.yaml`):
```yaml
dataset: 3dva
obj_subdir: 3DModels-Simplif-up         # which OBJ folder to use
extra_rotate_x_deg: 0.0
recenter_to_bbox_center: true
override_fov_deg: null                   # null = use JSON value (60° for 3DVA)

paths:
  dataset_root: ${VISUAL_ATTENTION_3D_SHAPES_ROOT}
  csv_root:     ${THREE_DVA_CSV_ROOT}
  json_root:    ${THREE_DVA_JSON_ROOT}
  output_dir:   results/3dva/cone_gaussian

method: cone_gaussian_on_mesh            # or: raycast_nearest_vertex
method_params:
  sigma_deg: 1.0
  radius_sigma_mult: 3.0

metrics:                                 # which metrics to compute
  - CC
  - NSS
  - KL
  - AUC_Judd

models:                                  # null = run all models found in csv_root
  - bunny
  - chair107
  - flowerpot
```

`run_benchmark.py` reads the config, resolves env vars, iterates over models,
calls the method function, computes metrics, writes `results.json`.

**Pros:**
- Zero code changes to switch parameters — edit YAML only
- Each config file is a reproducible experiment record
- Existing method modules stay unchanged; runner just imports them
- Easy to add a new metric: add to `metrics:` list in YAML

**Cons:**
- One more layer of indirection
- YAML parsing needs to be written

---

## Option B — Modular pipeline stages (pipeline/)

Each stage is a separate script that reads/writes intermediate `.npz` files:

```
pipeline/
  01_load_mesh.py      # OBJ → verts.npy, faces.npy, scale.json
  02_load_gaze.py      # CSV + JSON → per_frame_gaze.npz
  03_project.py        # verts + gaze → saliency_map.npy  (choose method)
  04_evaluate.py       # saliency_map + GT → metrics.json
```

Each stage is independent. You can:
- Re-run only the projection without reloading gaze data
- Swap the method (step 03) without touching 01, 02, or 04
- Add a metric (step 04) without touching the projection

**Pros:**
- Maximum independence — changing one stage does NOT affect others
- Easy to debug: inspect intermediate `.npz` files
- Best for research: can quickly try a new method in step 03

**Cons:**
- More files, more disk I/O (intermediate arrays)
- Requires a shell script or Makefile to chain the stages

---

## Option C — Shell batch wrapper (minimal change, fastest to use today)

No new Python code. Just a shell script that calls existing eval scripts in a loop:

```bash
#!/bin/bash
# run_3dva_cone.sh
source test/env/local_paths.example.sh
for MODEL in bunny chair107 flowerpot camel cow; do
    python3 reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py \
        --model "$MODEL" \
        --dataset-root "$REPROJECT_DATASET_3DVA_ROOT" \
        --csv-root    "$REPROJECT_GAZE_CSV_3DVA_ROOT" \
        --json-root   "$REPROJECT_GAZE_JSON_3DVA_ROOT" \
        --recenter-to-bbox-center \
        --output-dir  "results/3dva/cone_gaussian/$MODEL"
done
```

**Pros:** zero new code, works immediately, uses existing well-tested scripts
**Cons:** metrics and parameters are not in a config file; harder to track experiments

---

## Recommendation

**Start with Option C + transition to Option A.**

1. Use Option C (shell loops) for the first full 3DVA eval run — it needs nothing new.
2. In parallel, build `run_benchmark.py` (Option A) around the existing eval scripts.
3. Option B is best long-term for research; implement when the pipeline is stable.

---

## How methods currently relate to each other

```
reprojection_methods/
  cone_projection_on_mesh/
    eval_3dva_raycast_cone.py          # 3DVA, per-vertex, cone + raycast
    eval_meshmamba_cone.py             # MeshMamba, per-face, cone + raycast
    eval_geodesic_diffusion.py         # any dataset, per-face, geodesic smoothing
    eval_visual_attention_style_...py  # Saliency3D-style on mesh
  screen_space_gaussian/
    eval_meshmamba_screen_space.py     # MeshMamba, screen-space Gaussian blur
    eval_holdout_screenspace.py        # holdout baseline

metrics/
  common.py        # CC, KL, NSS, AUC, Similarity — shared by all methods
  mesh_space.py    # mesh-space: AUC_visible_top20, map_metrics
  screen_space.py  # screen-space: cc_from_maps, kl_from_maps
```

Methods **do not depend on each other**. They all import from `metrics/`.
Adding a new method = add a new file in `reprojection_methods/`, import from `metrics/`.

---

## Quick start for Option C (run 3DVA eval today)

```bash
source test/env/local_paths.example.sh

python3 reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py \
    --model bunny \
    --dataset-root "$REPROJECT_DATASET_3DVA_ROOT" \
    --csv-root     "$REPROJECT_GAZE_CSV_3DVA_ROOT" \
    --json-root    "$REPROJECT_GAZE_JSON_3DVA_ROOT" \
    --recenter-to-bbox-center \
    --output-dir   results/3dva/cone_gaussian/bunny
```

Key parameters:
- `--recenter-to-bbox-center` — required for correct 3DVA alignment
- `--extra-rotate-x-deg 0.0` — default, correct for `-up` OBJ files
- `--override-fov-deg` — omit (default None = use JSON FOV = 60°)
- `--sigma-deg 1.0` — angular uncertainty cone radius

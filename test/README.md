# Test Workspace — Alignment & Validation

This directory contains scripts and manifests for verifying that gaze-projection
eval scripts operate on the same geometric view that participants actually saw in the video.

---

## Directory layout

```
test/
├── blender_canonical/          Blender-based gold-standard rendering + batch IoU checks
│   ├── evaluate_blender_mask_batch.py   batch: run Blender render → compare mask vs video
│   ├── render_preview_from_manifest_blender.py   single Blender render
│   └── search_blender_alignment.py     Blender-based grid search (rotX × FOV)
├── overlay_alignment/          Python-based fast search and overlay visualisation
│   ├── search_preview_alignment.py     grid search (rotX × FOV, trimesh renderer)
│   └── overlay_video_and_preview.py    side-by-side and edge overlay helpers
├── tools/
│   └── render_preview_from_manifest.py   Python/trimesh preview renderer
├── manifests/                  per-model manifest JSONs (see section below)
├── env/
│   ├── local_paths.example.sh          local env-var definitions
│   └── vg_intellect_paths.example.sh   server env-var definitions
├── launch/                     shell wrappers for common batch tasks
└── output_local/               local results (gitignored large artifacts)
```

---

## Alignment check concept

**Goal:** confirm that the 3D-to-2D projection used by eval scripts overlaps precisely
with the object silhouette in the original video shown to participants.

**Metric:** mask IoU + composite score:
```
score = IoU - 0.50 * centroid_error_norm - 0.25 * size_error_norm
```

**Acceptance thresholds:**

| IoU   | Verdict |
|-------|---------|
| ≥ 0.90 | ✅ accepted without caveats |
| 0.80–0.89 | ⚠️ accepted with note in metadata |
| 0.70–0.79 | ⚠️ accepted conditionally — mention in paper |
| < 0.70 | 🔴 exclude from main results |

---

## Two check paths

### Path A — Python / trimesh (fast, same code as eval scripts)

Uses `render_preview_from_manifest.py` (the same projection code used by the actual
eval scripts `eval_meshmamba_cone.py`, `eval_meshmamba_screen_space.py`, etc.).

**Single manifest:**
```bash
source test/env/local_paths.example.sh
python3 test/tools/render_preview_from_manifest.py \
    --manifest test/manifests/preview_meshmamba_non_texture_starfruit.json
```

**Grid search (find best rotX + FOV):**
```bash
source test/env/local_paths.example.sh
python3 test/overlay_alignment/search_preview_alignment.py \
    --manifest test/manifests/preview_meshmamba_non_texture_starfruit.json \
    --output-dir test/output_local/overlay_search/starfruit_nt \
    --rot-x-start -120 --rot-x-stop 120 --rot-x-step 5 \
    --fov-start 28 --fov-stop 55 --fov-step 1
```
Reads `alignment_search_report.json` + visual overlays in `output-dir`.

### Path B — Blender canonical (gold standard)

Imports the OBJ in Blender with exactly the same axis convention as the original
render script, restores camera from JSON, and renders a PNG for direct comparison.

**Single manifest:**
```bash
source test/env/local_paths.example.sh
/Applications/Blender.app/Contents/MacOS/Blender \
    --background --factory-startup \
    --python test/blender_canonical/render_preview_from_manifest_blender.py \
    -- --manifest test/manifests/preview_meshmamba_non_texture_starfruit.json
```

**Batch (multiple manifests → IoU summary):**
```bash
source test/env/local_paths.example.sh
python3 test/blender_canonical/evaluate_blender_mask_batch.py \
    --manifest \
        test/manifests/preview_meshmamba_non_texture_penguin.json \
        test/manifests/preview_meshmamba_non_texture_moai.json \
        test/manifests/preview_meshmamba_non_texture_seahorse.json \
        test/manifests/preview_meshmamba_non_texture_rhinoceros.json \
    --output-dir test/output_local/blender_mask_batch_meshmamba_extended \
    --blender-bin /Applications/Blender.app/Contents/MacOS/Blender
```
Writes `summary.json` + per-model `overlay_edges.png` / `overlay_alpha.png`.

---

## Manifests

Each `manifests/preview_*.json` file describes one model check point:

| Key | Purpose |
|-----|---------|
| `dataset` | `"MeshMamba_non_texture"`, `"MeshMamba_rgb_texture"`, `"3DVA"` |
| `model` | model name (matches folder name in dataset) |
| `obj_path` | OBJ file via env-var placeholder |
| `json_path` | per-video camera+animation JSON |
| `video_path` | source video for frame extraction |
| `frame_index` | video frame to use for the comparison |
| `resolution_scale` | 0.5 = half resolution (960×540 for 1920×1080 sources) |
| `recenter_to_bbox_center` | must be `true` for all datasets |
| `extra_rotate_x_deg` | corrective X rotation; `90.0` for MeshMamba, per-model for 3DVA |
| `override_fov_deg` | override projection FOV; `37.5` for MeshMamba |

### Currently available manifests

**MeshMamba non_texture** (all use `rotX=90°`, `FOV=37.5°`):
- `preview_meshmamba_non_texture_starfruit.json` — Starfruit_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_non_texture_mango.json` — Mango_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_non_texture_pear.json` — Pear_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_non_texture_rubber_duck.json` — Rubber_Duck_v1_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_non_texture_penguin.json` — Penguin_V2_L3 ✅ IoU=0.988 (validated)
- `preview_meshmamba_non_texture_moai.json` — Moai_v3_L3 ✅ IoU=0.991 (validated)
- `preview_meshmamba_non_texture_seahorse.json` — SeaHorse_v2_L3 ✅ IoU=0.976 (validated, thin model)
- `preview_meshmamba_non_texture_rhinoceros.json` — Rhinoceros_v1_L3 ✅ IoU=0.987 (validated)

**MeshMamba rgb_texture** (same recipe):
- `preview_meshmamba_rgb_texture_starfruit.json` — Starfruit_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_rgb_texture_mango.json` — Mango_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_rgb_texture_pear.json` — Pear_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_rgb_texture_rubber_duck.json` — Rubber_Duck_v1_L3 ✅ IoU≈0.99 (validated)
- `preview_meshmamba_rgb_texture_penguin.json` — Penguin_V2_L3 ✅ IoU=0.992 (validated)
- `preview_meshmamba_rgb_texture_moai.json` — Moai_v3_L3 ✅ IoU=0.997 (validated)
- `preview_meshmamba_rgb_texture_seahorse.json` — SeaHorse_v2_L3 ✅ IoU=0.990 (validated)
- `preview_meshmamba_rgb_texture_rhinoceros.json` — Rhinoceros_v1_L3 ✅ IoU=0.992 (validated)

**3DVA — legacy (wrong OBJ, do not use for eval):**
- `preview_3dva_bunny.json` — bunny, `rotX=-70°`, `FOV=34°` — 🔴 IoU≈0.72 (wrong OBJ file)
- `preview_3dva_flowerpot.json` — flowerpot, `rotX=0°`, `FOV=37.5°` — 🔴 IoU≈0.85 (wrong OBJ file)
- `preview_3dva_chair107.json` — chair107, `rotX=0°`, `FOV=37.5°` — 🔴 IoU≈0.32 (wrong OBJ file)

**3DVA — corrected (`-up` OBJ, `rotX=0°`, `FOV=60°` from JSON):**

All 32 models validated. Recipe: `obj_path` → `3DModels-Simplif-up/`, `extra_rotate_x_deg=0.0`, `override_fov_deg=null` (uses JSON FOV=60°).

| Model | IoU | Status | | Model | IoU | Status |
|-------|-----|--------|-|-------|-----|--------|
| fandisk | 0.984 | ✅ | | gorgoile | 0.973 | ✅ |
| casting | 0.979 | ✅ | | house | 0.979 | ✅ |
| bunny | 0.978 | ✅ | | car-vasa | 0.975 | ✅ |
| turbine | 0.978 | ✅ | | flowerpot | 0.956 | ✅ |
| carter | 0.977 | ✅ | | vase-15k | 0.954 | ✅ |
| blade-200K | 0.971 | ✅ | | bimba | 0.953 | ✅ |
| meca-15k | 0.970 | ✅ | | prot | 0.947 | ✅ |
| torso | 0.968 | ✅ | | horse-110k | 0.946 | ✅ |
| rockerarm | 0.965 | ✅ | | chair107 | 0.933 | ✅ |
| hand-35K | 0.966 | ✅ | | james | 0.941 | ✅ |
| jessi | 0.934 | ✅ | | michael8 | 0.937 | ✅ |
| michael3 | 0.923 | ✅ | | dragon | 0.932 | ✅ |
| Max-Planck | 0.929 | ✅ | | cow | 0.922 | ✅ |
| camel | 0.916 | ✅ | | A380 | 0.907 | ✅ |
| Harley | 0.912 | ✅ | | octopus | 0.891 | ⚠️ thin tentacles |
| igea-100K | 0.888 | ⚠️ hair detail | | dinosaur-40K | 0.875 | ⚠️ self-shadow |

**Mean IoU = 0.946. 29/32 ≥ 0.90 ✅. 3/32 in 0.875–0.891 (accepted with note).** No models excluded.

---

## Adding a new MeshMamba manifest

1. Copy an existing manifest (e.g. `preview_meshmamba_non_texture_starfruit.json`).
2. Update `model`, `obj_path`, `json_path`, `video_path`, `output_prefix`.
3. Keep `extra_rotate_x_deg: 90.0`, `override_fov_deg: 37.5`, `recenter_to_bbox_center: true`.
4. Run the Blender batch check to confirm IoU ≥ 0.90.
5. If IoU < 0.90, run the grid search to find the correct `extra_rotate_x_deg` and `override_fov_deg`.

OBJ path pattern for MeshMamba:
```
${REPROJECT_DATASET_MESHMAMBA_ROOT}/MeshFile/non_texture/<ModelFolder>/<file>.obj
```
The folder name is the model name (`Penguin_V2_L3`). The OBJ filename inside can differ
(check `ls` in the folder). JSON and video filenames use the pattern:
```
MeshMamba_non_texture_<ModelFolder>.json
MeshMamba_non_texture_<ModelFolder>.mp4
```

---

## 3DVA alignment — root cause and resolution ✅ RESOLVED

### Root cause (discovered and fixed)

The render script (`3dva_render_1.py`) reads models from:
```
/mnt/hd2/29d_kon/projects/Rendering/Dataset/3DVA/3DModels-Simplif-up/
```

The `-up` suffix means the models were **manually pre-rotated** so they appear
upright after Blender's `forward='X', up='Z'` axis import. The published dataset
ships only `3DModels-Simplif/` without the pre-rotation.

### Key finding

Kabsch rigid-body analysis confirmed: **`3DModels-Simplif-up/` is the same mesh
as `3DModels-Simplif/`, just rotated** (Frobenius norm ratio = 1.000000 exactly,
max vertex residual < 2×10⁻⁶). The rotations are non-trivial and multi-axis:

| Model | Rotation local→up (world space) |
|-------|----------------------------------|
| bunny | rotX=-11°, rotY=-51°, rotZ=+9° |
| chair107 | rotY≈90°, rotZ≈-139° |
| flowerpot | rotZ≈-10° (nearly identical) |

This is why single-axis `rotX` grid search was unable to reach IoU ≥ 0.90:
the correct correction requires multi-axis rotation, not just X.

### Resolution

All 32 `-up` OBJ files downloaded from `vg-iai` server to:
```
${REPROJECT_DATASET_3DVA_ROOT}/3DModels-Simplif-up/
```

Manifests updated to `preview_3dva_<model>_up.json` with:
- `obj_path` → `3DModels-Simplif-up/<model>.obj`
- `extra_rotate_x_deg: 0.0`
- `override_fov_deg: null` (uses JSON FOV = 60°)

`eval_3dva_raycast_cone.py` updated: `3DModels-Simplif` → `3DModels-Simplif-up`.

**Result: mean IoU = 0.946 across 32 models. All models ≥ 0.875 (0 excluded).**

---

## Quick reference — environment variables

```bash
# Required before any test script
source test/env/local_paths.example.sh

# Key variables
REPROJECT_DATASET_MESHMAMBA_ROOT   # MeshMamba dataset root
REPROJECT_DATASET_3DVA_ROOT        # 3DVA dataset root
REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT
REPROJECT_GAZE_JSON_MESHMAMBA_RGB_TEXTURE_ROOT
REPROJECT_GAZE_JSON_3DVA_ROOT
REPROJECT_VIDEO_MESHMAMBA_NON_TEXTURE_ROOT
REPROJECT_VIDEO_MESHMAMBA_RGB_TEXTURE_ROOT
REPROJECT_VIDEO_3DVA_ROOT
REPROJECT_OUTPUT_ROOT
```

---

## Validated results summary

### MeshMamba (Blender canonical, 3 frames per model)

| Dataset | Model | Frames checked | IoU range | Status |
|---------|-------|---------------|-----------|--------|
| non_texture | Mango_L3 | 0, 200, 400 | 0.991–0.992 | ✅ |
| non_texture | Pear_L3 | 0, 200, 400 | 0.987–0.988 | ✅ |
| non_texture | Rubber_Duck_v1_L3 | 0, 200, 400 | 0.989–0.991 | ✅ |
| non_texture | Starfruit_L3 | 0–400 | 0.990–0.992 | ✅ |
| non_texture | Penguin_V2_L3 | 0 | 0.988 | ✅ |
| non_texture | Moai_v3_L3 | 0 | 0.991 | ✅ |
| non_texture | SeaHorse_v2_L3 | 0 | 0.976 | ✅ |
| non_texture | Rhinoceros_v1_L3 | 0 | 0.987 | ✅ |
| rgb_texture | Mango_L3 | 0, 200, 400 | 0.997–0.998 | ✅ |
| rgb_texture | Pear_L3 | 0, 200, 400 | 0.995–0.996 | ✅ |
| rgb_texture | Rubber_Duck_v1_L3 | 0, 200, 400 | 0.988–0.997 | ✅ |
| rgb_texture | Starfruit_L3 | 0–400 | 0.996–0.997 | ✅ |
| rgb_texture | Penguin_V2_L3 | 0 | 0.992 | ✅ |
| rgb_texture | Moai_v3_L3 | 0 | 0.997 | ✅ |
| rgb_texture | SeaHorse_v2_L3 | 0 | 0.990 | ✅ |
| rgb_texture | Rhinoceros_v1_L3 | 0 | 0.992 | ✅ |

### 3DVA (Blender canonical, frame 0, `-up` OBJ, `rotX=0°`, `FOV=60°`)

All 32 models validated with `3DModels-Simplif-up/` OBJ files:

| Model | IoU | | Model | IoU |
|-------|-----|-|-------|-----|
| fandisk | 0.984 ✅ | | turbine | 0.978 ✅ |
| casting | 0.979 ✅ | | house | 0.979 ✅ |
| bunny | 0.978 ✅ | | gorgoile | 0.973 ✅ |
| carter | 0.977 ✅ | | car-vasa | 0.975 ✅ |
| blade-200K | 0.971 ✅ | | flowerpot | 0.956 ✅ |
| meca-15k | 0.970 ✅ | | vase-15k | 0.954 ✅ |
| hand-35K | 0.966 ✅ | | bimba | 0.953 ✅ |
| torso | 0.968 ✅ | | prot | 0.947 ✅ |
| rockerarm | 0.965 ✅ | | horse-110k | 0.946 ✅ |
| james | 0.941 ✅ | | jessi | 0.934 ✅ |
| michael8 | 0.937 ✅ | | chair107 | 0.933 ✅ |
| dragon | 0.932 ✅ | | Max-Planck | 0.929 ✅ |
| cow | 0.922 ✅ | | michael3 | 0.923 ✅ |
| camel | 0.916 ✅ | | A380 | 0.907 ✅ |
| Harley | 0.912 ✅ | | octopus | 0.891 ⚠️ |
| igea-100K | 0.888 ⚠️ | | dinosaur-40K | 0.875 ⚠️ |

**Mean IoU = 0.946 · 29/32 ✅ ≥ 0.90 · 3/32 ⚠️ (0.875–0.891, accepted with note) · 0/32 🔴**

The 3 models below 0.90 have geometric alignment confirmed as correct — lower IoU
is from rendering artefacts (octopus: thin tentacles, igea-100K: hair texture,
dinosaur-40K: strong Cycles self-shadows on limbs).

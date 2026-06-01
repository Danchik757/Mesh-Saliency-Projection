# Datasets Reference

Datasets are **not stored in this repository**. They are distributed as ZIP archives
attached to the [GitHub Release `v1.0-data`](https://github.com/Danchik757/Mesh-Saliency-Projection/releases/tag/v1.0-data).

Reference spreadsheet: [Dataset table (Google Sheets)](https://docs.google.com/spreadsheets/d/1UpTHzfqAma46_czqMvlA_15AVIm5T2Em6d_BmskiCkQ/edit?gid=881515507#gid=881515507)

---

## Quick download

```bash
# Download all core datasets (~476 MB compressed) to a local folder
bash scripts/download_datasets.sh --data-root /path/to/data

# Then configure env vars for this machine:
cp test/env/new_machine.env.sh.template test/env/local_paths.sh
# Set DATA_ROOT= in local_paths.sh, then:
source test/env/local_paths.sh
```

Optional extras:
```bash
--with-videos         # +256 MB rendered MP4 (needed for alignment checks)
--with-smooth-gaze    # +~2 GB SAL3D auxiliary neighbour lists
```

---

## Storage overview

| ZIP in release | Compressed | Uncompressed | Contents |
|----------------|-----------|--------------|----------|
| `3dva_objs.zip` | 16 MB | ~50 MB | 32 OBJ meshes (corrected orientation) |
| `3dva_gt.zip` | 36 MB | ~8 MB | GT fixation maps + centricity maps |
| `meshmamba_non_texture_objs.zip` | 80 MB | ~279 MB | 105 OBJ meshes (no texture) |
| `meshmamba_rgb_texture_objs.zip` | 128 MB | ~379 MB | 105 OBJ meshes (RGB texture) |
| `meshmamba_saliency_gt.zip` | 19 MB | ~60 MB | Per-face GT saliency CSV |
| `sal3d_meshes.zip` | 97 MB | ~282 MB | 57 OBJ meshes |
| `sal3d_gaze.zip` | 50 MB | ~226 MB | 58 raw gaze files (.txt) |
| `gaze_csv_3dva.zip` | 8.4 MB | ~38 MB | 32 eye-tracker CSV recordings |
| `gaze_csv_meshmamba.zip` | 38 MB | ~176 MB | 105+105 eye-tracker CSV recordings |
| `camera_jsons.zip` | 4.3 MB | ~25 MB | Camera/animation JSON for all datasets |
| *(optional)* `sal3d_smooth_gaze.zip` | ~500 MB | ~2.5 GB | SAL3D auxiliary smoothing data |
| *(optional)* `videos_*.zip` | ~256 MB | ~256 MB | Rendered MP4 per dataset |
| **Total (core)** | **~476 MB** | **~1.5 GB** | |

---

## Dataset 1 — 3DVA

### Overview

| Property | Value |
|----------|-------|
| Source | Published dataset (3D Visual Attention) |
| Models | 32 OBJ meshes |
| GT type | Per-vertex fixation maps |
| GT format | `.txt`, one float per line, normalised to [0, 1] |
| GT views | 3 static viewpoints per model (frames 300, 413, 599) |
| GT filename | `<model>_300norm.txt`, `<model>_413norm.txt`, `<model>_599norm.txt` |
| Participants | External (from original dataset) |

### File counts and sizes (uncompressed)

| Subfolder | Files | Size |
|-----------|-------|------|
| `3DVA/3DModels-Simplif-up/` | 32 `.obj` | ~50 MB |
| `3DVA/FixationMaps/` | 96 `.txt` (32 models × 3 views) | ~7.8 MB |
| `3DVA/CentricityAndVisibilityMaps/` | — | — |
| `gaze_csv/3DVA/` | 32 `.csv` | ~38 MB |
| `jsons_for_models/3DVA_json/` | 32 `.json` | — |
| `videos/3DVA/` | 32 `.mp4` | ~76 MB |

### Important: OBJ orientation

Use **only** `3DModels-Simplif-up/` (corrected orientation).
The original `3DModels-Simplif/` (published dataset) has wrong orientation —
each model is pre-rotated by a different non-trivial multi-axis rotation.

Verified via Kabsch rigid-body analysis: same geometry, Frobenius norm ratio = 1.000000,
max vertex residual < 2×10⁻⁶. The rotations are non-trivial and different per model
(e.g., bunny: rotX=−11°, rotY=−51°, rotZ=+9°; chair107: rotY≈90°, rotZ≈−139°).

The render script used `forward='X'`, `up='Z'` axis import in Blender.

### JSON structure (`3DVA_<model>.json`)

```json
{
  "camera_static": {
    "view_matrix": [16 floats, row-major 4×4],
    "fov_degrees": 60.0
  },
  "video_info": {
    "fps": 25,
    "total_frames": 625,
    "width": 1920,
    "height": 1080
  },
  "frames": [
    { "rotation_z_radians": 0.0 },
    { "rotation_z_radians": 0.01005 },
    ...
  ]
}
```

### Gaze CSV structure

Each `<model>.csv` contains one row per participant-frame pair:

| Column | Type | Description |
|--------|------|-------------|
| `participant_id` | str | Participant identifier |
| `frame` | int | Video frame index (0-based) |
| `data_gazes` | JSON str | `[{"t": ms, "x": 0–1, "y": 0–1}, ...]` |

`x`, `y` are normalised screen coordinates (0 = left/top, 1 = right/bottom).

### Alignment validation

All 32 models validated with Blender canonical mask IoU check:

| Metric | Value |
|--------|-------|
| Mean IoU | **0.946** |
| Min IoU | 0.875 (dinosaur-40K — strong Cycles self-shadow on limbs) |
| Models ≥ 0.90 | 29/32 ✅ |
| Models 0.875–0.889 | 3/32 ⚠️ (rendering artefacts, not alignment errors) |
| Models excluded | **0** |

Recipe: `extra_rotate_x_deg=0.0`, `override_fov_deg=null` (reads FOV=60° from JSON),
`recenter_to_bbox_center=true`.

---

## Dataset 2 — MeshMamba

### Overview

| Property | Value |
|----------|-------|
| Source | Published dataset (MeshMamba Saliency) |
| Tracks | 2: `non_texture` and `rgb_texture` |
| Models | 105 per track |
| Faces per model | 32 868 (fixed for all models) |
| GT type | Per-face saliency |
| GT format | `.csv`, one float per line (32 868 values) |
| Participants | External (from original dataset) |

### File counts and sizes (uncompressed)

| Subfolder | Files | Size |
|-----------|-------|------|
| `MeshMamba/MeshFile/non_texture/` | 105 model folders | ~279 MB |
| `MeshMamba/MeshFile/rgb_texture/` | 105 model folders | ~379 MB |
| `MeshMamba/SaliencyMap/non_texture/` | 105 `.csv` | — |
| `MeshMamba/SaliencyMap/rgb_texture/` | 105 `.csv` | — |
| `gaze_csv/MeshMamba_non_texture/` | 105 `.csv` | ~81 MB |
| `gaze_csv/MeshMamba_rgb_texture/` | 105 `.csv` | ~95 MB |
| `jsons_for_models/Mamba_non_textured/` | 105 `.json` | — |
| `jsons_for_models/Mamba_rgb_textured/` | 105 `.json` | — |
| `videos/MeshMamba_non_texture/` | 105 `.mp4` | ~48 MB |
| `videos/MeshMamba_rgb_texture/` | 105 `.mp4` | ~61 MB |

### OBJ file naming

Each model lives in its own subfolder named after the model.
The OBJ filename inside can differ — always find it with `ls`:

```
MeshFile/non_texture/Rubber_Duck_v1_L3/rubber_duck.obj
MeshFile/non_texture/Penguin_V2_L3/Penguin_V2_L3.obj
```

### JSON structure (`MeshMamba_non_texture_<model>.json`)

```json
{
  "camera_static": {
    "view_matrix": [16 floats, row-major 4×4],
    "fov_degrees": 75.0
  },
  "video_info": {
    "fps": 25,
    "total_frames": 510,
    "width": 1920,
    "height": 1080
  },
  "frames": [
    { "rotation_z_radians": 0.0 },
    { "rotation_z_radians": 0.01234 },
    ...
  ]
}
```

The object **rotates** between frames (`rotation_z_radians` changes per frame).
Gaze density must be computed **per-frame** (not pooled across all frames).

### Gaze CSV structure

Same format as 3DVA: columns `participant_id`, `frame`, `data_gazes` (`{t, x, y}`).

### Alignment validation

8 representative models validated with Blender canonical check (3 frames each):

| Track | Models checked | IoU range | Status |
|-------|---------------|-----------|--------|
| non_texture | 8/105 | 0.976–0.992 | ✅ all ≥ 0.976 |
| rgb_texture | 8/105 | 0.988–0.998 | ✅ all ≥ 0.988 |

Recipe uniform across all 105 models: `extra_rotate_x_deg=90.0`,
`override_fov_deg=37.5`, `recenter_to_bbox_center=true`.

The remaining 97 models were not individually checked but use the same
render script and axis convention — recipe is uniform.

### Full benchmark results (105 models)

| Track | Method | CC mean (all) | CC mean (excl. CC<0) | Models with CC<0 |
|-------|--------|--------------|----------------------|-----------------|
| non_texture | screen_space_gaussian v1 | 0.136 | 0.218 | 26/105 |
| non_texture | cone_gaussian_on_mesh | 0.321 | 0.372 | 11/105 |
| rgb_texture | screen_space_gaussian v1 | 0.130 | 0.219 | 29/105 |
| rgb_texture | cone_gaussian_on_mesh | 0.274 | 0.343 | 15/105 |

---

## Dataset 3 — SAL3D

### Overview

| Property | Value |
|----------|-------|
| Source | Published dataset (SAL3D) |
| Models | 57 OBJ meshes |
| GT type | Per-vertex raw gaze hits |
| GT format | `.txt`, 8 columns per line (space-separated) |
| Participants | External (from original dataset) |

### File counts and sizes (uncompressed)

| Subfolder | Files | Size |
|-----------|-------|------|
| `SAL3D/Meshes/` | 57 `.obj` | ~282 MB |
| `SAL3D/Gaze/` | 58 `.txt` raw gaze | ~226 MB |
| `SAL3D/Smooth_Gaze/` | 53 files (optional) | **~2.0 GB** |
| `jsons_for_models/SAL3D_json/` | 57 `.json` | — |
| `videos/SAL3D/` | 57 `.mp4` | ~71 MB |

### Raw gaze format (`SAL3D/Gaze/<model>.txt`)

8 columns per line (space-separated):

```
participant_id  frame  x  y  z  vertex_index  weight  timestamp_ms
```

### Smooth_Gaze (auxiliary — not ground truth)

`SAL3D/Smooth_Gaze/<model>_neighbors.txt` contains pre-computed vertex-neighbour
lists for geodesic smoothing. These are **not** the GT saliency map — they are
auxiliary data for one smoothing approach. Skip if not specifically needed (~2.0 GB).

Note: two directories exist on the original machine due to a naming inconsistency:
- `Smooth_Gaze/` (underscore) — 2.0 GB, primary
- `Smooth Gaze/` (space) — ~480 MB, a partial subset

Only `Smooth_Gaze/` is included in `sal3d_smooth_gaze.zip`.

### JSON structure (`Sal3D_<model>.json`)

Same format as 3DVA/MeshMamba. Key difference: Blender render used
`forward_axis='Z'`, `up_axis='Y'` (vs 3DVA: `forward='X'`, `up='Z'`).

```json
{
  "camera_static": { "view_matrix": [16 floats], "fov_degrees": 60.0 },
  "video_info": { "fps": 25, "total_frames": 550, "width": 1920, "height": 1080 },
  "frames": [ { "rotation_z_radians": 0.0 }, ... ]
}
```

Camera position: `(0, -1.5, bbox_height/2 + 0.5)` in world space.
Start angle is deterministic (SHA256 seed from model name).

### Critical: GT vertex coverage mismatch

35 of 57 SAL3D models have high-resolution OBJ (>20 K vertices) while
GT covers only 20 K vertices. Unmatched OBJ vertices receive GT=0,
which inflates the denominator and distorts CC/SIM by 50–130%.

**Rule:** always use `metrics_vs_gt_covered_only` from eval output JSON.
Never use `metrics_vs_gt_full_mesh` for comparison tables.
The `gt_match_type` field marks each model as `"direct"` or `"subset"`.

### Alignment validation

All 57 models validated with Blender canonical check (frame 0):

| Metric | Value |
|--------|-------|
| Mean IoU | **0.977** |
| Min IoU | 0.907 (octopus — thin geometry) |
| Models ≥ 0.90 | **57/57** ✅ |
| Models excluded | **0** |

Recipe: `extra_rotate_x_deg=90.0`, `override_fov_deg=null` (uses JSON FOV=60°),
`forward_axis='Z'`, `up_axis='Y'`, `recenter_to_bbox_center=true`.

### Coverage gaps

| Issue | Models | Action |
|-------|--------|--------|
| Gaze file but no OBJ | AudiRS5, bimba, blade | Ignore |
| No gaze and no smooth_gaze | gamecontroller, spanner | Skip in eval |
| No smooth_gaze only | MaxPlanck, dog, flowerpot, gamecontroller, prot, spanner | Skip smooth-gaze eval |

---

## Data sources

| Data | Who produced it | Format |
|------|----------------|--------|
| OBJ meshes | Original dataset authors | `.obj` |
| GT saliency (all 3 datasets) | Original dataset authors | `.txt` / `.csv` |
| **Gaze CSV recordings** | **Our lab (eye-tracker study)** | `.csv` |
| **Camera JSON params** | **Our lab (Blender render scripts)** | `.json` |
| **Rendered videos** | **Our lab** | `.mp4` |

Our eye-tracker recordings cover MeshMamba (105+105 models) and 3DVA (32 models).
Camera JSONs encode the Blender camera used for rendering — they are not part
of the original published datasets.

---

## Directory structure after download

After `bash scripts/download_datasets.sh --data-root /path/to/data`:

```
$DATA_ROOT/
├── 3DVA/
│   ├── 3DModels-Simplif-up/        32 OBJ (corrected orientation — use these)
│   ├── FixationMaps/               96 GT .txt (3 views × 32 models)
│   └── CentricityAndVisibilityMaps/
├── MeshMamba/
│   ├── MeshFile/
│   │   ├── non_texture/            105 model folders, each with 1 OBJ
│   │   └── rgb_texture/            105 model folders, each with 1 OBJ
│   └── SaliencyMap/
│       ├── non_texture/            105 GT .csv (32 868 values each)
│       └── rgb_texture/            105 GT .csv
├── SAL3D/
│   ├── Meshes/                     57 OBJ
│   ├── Gaze/                       58 raw gaze .txt
│   └── Smooth_Gaze/                53 neighbour lists (--with-smooth-gaze only)
├── gaze_csv/
│   ├── 3DVA/                       32 .csv  (our recordings)
│   ├── MeshMamba_non_texture/      105 .csv (our recordings)
│   └── MeshMamba_rgb_texture/      105 .csv (our recordings)
├── jsons_for_models/
│   ├── 3DVA_json/                  32 .json  (camera + animation params)
│   ├── Mamba_non_textured/         105 .json
│   ├── Mamba_rgb_textured/         105 .json
│   └── SAL3D_json/                 57 .json
└── videos/                         (--with-videos only)
    ├── 3DVA/                       32 .mp4
    ├── MeshMamba_non_texture/      105 .mp4
    ├── MeshMamba_rgb_texture/      105 .mp4
    └── SAL3D/                      57 .mp4
```

---

## See also

- [DATA_PATHS.md](../DATA_PATHS.md) — absolute paths on each specific machine
- [test/README.md](../test/README.md) — full alignment validation tables and IoU results
- [scripts/download_datasets.sh](../scripts/download_datasets.sh) — download script
- [scripts/package_datasets.sh](../scripts/package_datasets.sh) — packaging (maintainer only)

# Data Paths Reference

Last updated: 2026-05-30 (videos reorganized)

This file is the single reference for where every type of file lives,
both locally (macOS) and on the server (vg-iai).

---

## Environment setup

```bash
# Local — run before any test/ or eval script
source test/env/local_paths.example.sh
```

---

## LOCAL (macOS)

### 3DVA dataset

| Type | Path |
|------|------|
| OBJ files (corrected, pre-rotated) | `/Users/admin/Documents/LAB/Dataset/3DVA/3DModels-Simplif-up/` |
| OBJ files (original, wrong orientation) | `/Users/admin/Documents/LAB/Dataset/3DVA/3DModels-Simplif/` |
| GT fixation maps (per-vertex, .txt) | `/Users/admin/Documents/LAB/Dataset/3DVA/FixationMaps/` |
| Visibility/centricity maps | `/Users/admin/Documents/LAB/Dataset/3DVA/CentricityAndVisibilityMaps/` |
| Camera JSON (per-model) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/3DVA_json/` |
| Gaze CSV (per-model) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA/` |
| Video MP4 | `/Users/admin/Documents/LAB/SALIENCY_code/videos/3DVA/` |

File naming patterns (3DVA):
- OBJ: `<model>.obj` (e.g. `bunny.obj`, `chair107.obj`)
- JSON: `3DVA_<model>.json`
- CSV: `<model>.csv`
- MP4: `3DVA_<model>.mp4`
- GT: `<model>_300norm.txt`, `<model>_413norm.txt`, `<model>_599norm.txt`

### MeshMamba non_texture dataset

| Type | Path |
|------|------|
| OBJ files | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/non_texture/` |
| GT saliency maps (per-face) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/non_texture/` |
| Camera JSON (per-model) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/Mamba_non_textured/` |
| Gaze CSV (per-model) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_non_texture/` |
| Video MP4 | `/Users/admin/Documents/LAB/SALIENCY_code/videos/MeshMamba_non_texture/` |

### MeshMamba rgb_texture dataset

| Type | Path |
|------|------|
| OBJ files | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/MeshFile/rgb_texture/` |
| GT saliency maps (per-face) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/datasets/MeshMamba/MeshMambaSaliency/SaliencyMap/rgb_texture/` |
| Camera JSON (per-model) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/jsons_for_models/Mamba_rgb_textured/` |
| Gaze CSV (per-model) | `/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/MeshMamba_rgb_texture/` |
| Video MP4 | `/Users/admin/Documents/LAB/SALIENCY_code/videos/MeshMamba_rgb_texture/` |

File naming patterns (MeshMamba):
- OBJ: `<ModelFolder>/<filename>.obj` (folder = model name, filename can differ — check `ls`)
- JSON: `MeshMamba_non_texture_<ModelFolder>.json` or `MeshMamba_rgb_texture_<ModelFolder>.json`
- CSV: `<ModelFolder>.csv`
- MP4: `MeshMamba_non_texture_<ModelFolder>.mp4` or `MeshMamba_rgb_texture_<ModelFolder>.mp4`

### Python scripts (local repo)

| Role | Path |
|------|------|
| Repo root | `/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection/` |
| 3DVA cone eval | `reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py` |
| MeshMamba cone eval | `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py` |
| MeshMamba screen-space eval | `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py` |
| Geodesic diffusion eval | `reprojection_methods/cone_projection_on_mesh/eval_geodesic_diffusion.py` |
| Metrics package | `metrics/` |
| Alignment check (Blender) | `test/blender_canonical/evaluate_blender_mask_batch.py` |
| Alignment check (Python) | `test/overlay_alignment/search_preview_alignment.py` |
| Test manifests | `test/manifests/` |
| Env vars file | `test/env/local_paths.example.sh` |

---

## SERVER (vg-iai)

SSH alias: `vg-iai` → `vg-iai-1.lab.graphicon.ru`, user `29d_kon`

### 3DVA dataset (server)

| Type | Path |
|------|------|
| OBJ files (corrected) | `/mnt/hd2/29d_kon/projects/Rendering/Dataset/3DVA/3DModels-Simplif-up/` |
| OBJ files (original) | `/mnt/hd2/29d_kon/projects/Rendering/Dataset/3DVA/3DModels-Simplif/` |
| GT fixation maps | `/mnt/hd2/29d_kon/projects/Rendering/Dataset/3DVA/FixationMaps/` |
| Camera JSON (per-model) | `/mnt/hd2/29d_kon/projects/Rendering/3DVA/3dva_logs/non_mvp_data/` |
| Video MP4 | `/mnt/hd2/29d_kon/projects/Rendering/3DVA/3dva_videos/` |
| Gaze CSV | Not found server-side — use local CSV files as side input |

### MeshMamba dataset (server)

| Type | Path |
|------|------|
| OBJ files (non_texture) | `/mnt/hd2/29d_kon/projects/Rendering/Dataset/MeshMambaSaliency/MeshFile/non_texture/` |
| OBJ files (rgb_texture) | `/mnt/hd2/29d_kon/projects/Rendering/Dataset/MeshMambaSaliency/MeshFile/rgb_texture/` |
| GT saliency maps | `/mnt/hd2/29d_kon/projects/Rendering/Dataset/MeshMambaSaliency/SaliencyMap/` |
| Gaze CSV | `/mnt/hd2/29d_kon/projects/Rendering/MAMBA_GAZE/data/csv_for_models/` |
| Camera JSON | `/mnt/hd2/29d_kon/projects/Rendering/MAMBA_GAZE/data/` (check subfolders) |

### Python scripts (server)

| Role | Path |
|------|------|
| MeshMamba gaze entrypoint | `/mnt/hd2/29d_kon/projects/Rendering/MAMBA_GAZE/run_meshmamba_gaze.py` |
| MeshMamba pipeline package | `/mnt/hd2/29d_kon/projects/Rendering/MAMBA_GAZE/mamba_gaze/` |
| Python environment | `/mnt/hd2/29d_kon/environments/gaze_env/` |
| Activate env | `source /mnt/hd2/29d_kon/environments/gaze_env/bin/activate` |

---

## Side input workflow

Files that do NOT exist locally and must be transferred from server:

| File / Directory | Server path | Transfer command |
|-----------------|-------------|-----------------|
| 3DVA OBJ `-up` (done ✅) | `/mnt/hd2/29d_kon/projects/Rendering/Dataset/3DVA/3DModels-Simplif-up/` | `scp vg-iai:"path/*.obj" local/` |
| 3DVA gaze CSV | Unknown server location | Request from GPT |
| MeshMamba gaze CSV (all) | `/mnt/hd2/29d_kon/projects/Rendering/MAMBA_GAZE/data/csv_for_models/` | Transferred in earlier session |

---

## Key environment variables

```bash
REPROJECT_DATASET_3DVA_ROOT       # → /Users/admin/Documents/LAB/Dataset/3DVA
REPROJECT_DATASET_MESHMAMBA_ROOT  # → .../MeshMambaSaliency
REPROJECT_GAZE_JSON_3DVA_ROOT     # → .../jsons_for_models/3DVA_json
REPROJECT_GAZE_JSON_MESHMAMBA_NON_TEXTURE_ROOT
REPROJECT_GAZE_JSON_MESHMAMBA_RGB_TEXTURE_ROOT
REPROJECT_GAZE_CSV_3DVA_ROOT      # → .../csv_for_models/3DVA
REPROJECT_GAZE_CSV_MESHMAMBA_NON_TEXTURE_ROOT
REPROJECT_GAZE_CSV_MESHMAMBA_RGB_TEXTURE_ROOT
REPROJECT_VIDEO_3DVA_ROOT         # → .../SALIENCY_code/videos/3DVA
REPROJECT_VIDEO_MESHMAMBA_NON_TEXTURE_ROOT
REPROJECT_VIDEO_MESHMAMBA_RGB_TEXTURE_ROOT
REPROJECT_OUTPUT_ROOT             # → test/output_local
```

Full definitions: `test/env/local_paths.example.sh`

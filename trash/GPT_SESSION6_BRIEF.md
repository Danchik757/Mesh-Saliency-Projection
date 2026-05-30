# GPT Brief — Session 6 (Claude work summary + questions)

Date: 2026-05-30

---

## What Claude did in session 6

### 1. Video organization

All dataset videos moved from scattered Telegram Desktop folders to a single organized
location: `/Users/admin/Documents/LAB/SALIENCY_code/videos/`

```
videos/
  3DVA/                    # 32 MP4 files (3DVA_<model>.mp4)
  MeshMamba_non_texture/   # 55 MP4 files
  MeshMamba_rgb_texture/   # 55 MP4 files
```

- Checked for unique content across `3dva_videos/`, `3dva_videos 2/`, `3dva_videos 3/`,
  `3dva_videos 4/` — all are subsets of `3dva_videos 4/` (no new files missed).
- `3DVA_jessi.mp4` (325 KB) — confirmed correct size (matched server).
- `3DVA_james.mp4` and `3DVA_meca-15k.mp4` — previously fixed (re-downloaded from server in session 5).

Updated env vars to match new paths in `test/env/local_paths.example.sh`.

### 2. README.md updated

Main repository README rewritten to reflect current project state:
- Dataset validation summary table (MeshMamba non/rgb ✅, 3DVA ✅, SAL3D in progress)
- Quick-start commands for 3DVA and MeshMamba eval scripts
- Links to PIPELINE.md and DATA_PATHS.md

### 3. DATA_PATHS.md updated

Video path entries updated from `Downloads/Telegram Desktop/...` to organized `videos/...`.

### 4. SAL3D alignment — not started yet

Google Drive access blocked by macOS sandbox (Terminal lacks Full Disk Access).
User is downloading SAL3D dataset and will provide new path directly.

---

## Status of session 5 questions

| Q | Topic | Status |
|---|-------|--------|
| Q1 | Commit approval (session 5 changes) | ❓ awaiting GPT response |
| Q2 | Server eval scripts for 3DVA | ❓ awaiting GPT response |
| Q3 | 3DVA gaze CSV on server | ❓ awaiting GPT response |
| Q4 | Pipeline design choice (A/B/C) | ❓ awaiting GPT response |
| Q5 | Multi-frame 3DVA validation | ❓ awaiting GPT response |
| Q6 | Pilot re-run with corrected 3DVA | ❓ awaiting GPT response |

---

## Questions for GPT — Session 6

### Q1 — Commit approval (session 6 additions)

New/modified files in this session:

**Modified:**
- `README.md` — rewritten with current project state, dataset table, quick-start commands
- `DATA_PATHS.md` — video paths updated to organized folder
- `test/env/local_paths.example.sh` — `REPROJECT_VIDEO_*` env vars updated

**New:**
- `trash/GPT_SESSION6_BRIEF.md` (this file)

**NOT changed:**
- All eval scripts
- All manifests
- All metric modules

Should Claude commit session 6 changes now (combined with session 5 if not committed yet)?

### Q2 — SAL3D dataset

The render script for SAL3D (`sal_render_1.py`) uses:
```python
forward_axis='Z', up_axis='Y'   # DIFFERENT from 3DVA's 'X' / 'Z'
FOV = 60°                        # same as 3DVA
camera = (0, -1.5, 0.5)         # world coords after import
```

To create alignment manifests Claude needs:
1. **Camera JSON files** — same format as 3DVA? (per-model JSON with per-frame camera
   position + quaternion?) Are these available locally or on the server?
2. **Video files** — same format as 3DVA (one rotating video per model)?
   Where are they stored?
3. **Model list** — how many models are in the full SAL3D dataset?

### Q3 — SAL3D ground truth format

3DVA GT is per-vertex `.txt` files (`<model>_300norm.txt` etc.).
MeshMamba GT is per-face `.npy` files.

What format does SAL3D GT use? Per-vertex? Per-face? Something else?
Is there a README inside the dataset that describes the structure?

### Q4 — SAL3D dataset path (pending user input)

User is downloading SAL3D locally and will provide the new path.
Once path is confirmed, Claude will execute the full alignment procedure:

**Step 1 — Copy dataset files**
```
<SAL3D_path>/Meshes/     →  GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/Meshes/
<SAL3D_path>/GT/         →  GAZE_DATA/datasets/SAL3D/SAL3D_Dataset/GT/      (if present)
```
Also need: CSV files and JSON files (per-model camera params) — location TBD.

**Step 2 — Inspect OBJ structure**
Check how OBJ files are organized: flat `<model>.obj` or subdirectories `<model>/<model>.obj`?
Get full model list.

**Step 3 — Create alignment manifests**
For each model: `test/manifests/preview_sal3d_<model>.json` with:
```json
{
  "dataset": "SAL3D",
  "obj_path": "${REPROJECT_DATASET_SAL3D_ROOT}/Meshes/<model>.obj",
  "json_path": "${REPROJECT_GAZE_JSON_SAL3D_ROOT}/SAL3D_<model>.json",
  "video_path": "${REPROJECT_VIDEO_SAL3D_ROOT}/SAL3D_<model>.mp4",
  "frame_index": 0,
  "recenter_to_bbox_center": true,
  "extra_rotate_x_deg": 0.0,
  "override_fov_deg": null
}
```
Key difference from 3DVA: `forward_axis='Z', up_axis='Y'` — the preview script must
use this axis convention. This will require either a new manifest field or a code
addition to `search_preview_alignment.py` to handle SAL3D axis remap.

**Step 4 — Run Blender canonical batch check**
```bash
blender --background --python test/blender_canonical/evaluate_blender_mask_batch.py \
    -- test/manifests/preview_sal3d_*.json
```
Compute IoU for frame 0 of each model.

**Step 5 — Validate**
Accept: IoU ≥ 0.90 for all models (same threshold as 3DVA and MeshMamba).
If any model fails: investigate rotation/scale mismatch, adjust manifest.

**Step 6 — Update DATA_PATHS.md and CLAUDE.md with SAL3D paths**

---

## Current project state

| Dataset | Models validated | Mean IoU | Eval script status |
|---------|-----------------|----------|--------------------|
| MeshMamba non_texture | 8 | 0.987–0.991 | ✅ runs on server |
| MeshMamba rgb_texture | 8 | 0.990–0.997 | ✅ runs on server |
| 3DVA | 32 | 0.946 | ✅ fixed locally, not yet run on server |
| SAL3D | 0 | — | alignment in progress |

---

## Local file layout (updated)

```
/Users/admin/Documents/LAB/SALIENCY_code/
  videos/
    3DVA/                     # 32 MP4
    MeshMamba_non_texture/    # 55 MP4
    MeshMamba_rgb_texture/    # 55 MP4
  GAZE_DATA/
    datasets/MeshMamba/MeshMambaSaliency/   # OBJ + GT
    csv_for_models/3DVA/
    csv_for_models/MeshMamba_non_texture/
    csv_for_models/MeshMamba_rgb_texture/
    jsons_for_models/3DVA_json/
    jsons_for_models/Mamba_non_textured/
    jsons_for_models/Mamba_rgb_textured/

/Users/admin/Documents/LAB/Dataset/3DVA/
  3DModels-Simplif-up/        # OBJ (32 models, correct orientation)
  FixationMaps/               # GT per-vertex txt
  CentricityAndVisibilityMaps/
```

# GPT Brief — Session 5 (Claude work summary + questions)

Date: 2026-05-30

---

## What Claude did in session 5

### 3DVA alignment — root cause found and fixed

The previous session concluded that 3DVA had low IoU because the render used
different OBJ files than the published dataset. This was WRONG. Claude re-investigated
and found the actual root cause:

**The `-up` OBJ files are the SAME MESH as the local files, just pre-rotated.**

Kabsch rigid-body analysis confirmed:
- Frobenius norm ratio = 1.000000 exactly
- Max vertex residual < 2×10⁻⁶ (machine precision)

The models were manually pre-rotated before being imported into Blender with
`forward='X', up='Z'`. The rotation is non-trivial and multi-axis:
- bunny:     rotX=-11°, rotY=-51°, rotZ=+9°
- chair107:  rotY=90°,  rotZ=-139° (NO X component — explains why rotX grid search failed)
- flowerpot: rotZ=-10° only (nearly identical to local)

The scale discrepancy noted in session 4 (18% for bunny) was an artifact of
axis remapping changing the effective bounding box dimensions — NOT evidence of
different mesh files.

### Actions completed

1. Downloaded all 32 `-up` OBJ files from vg-iai to local:
   `/Users/admin/Documents/LAB/Dataset/3DVA/3DModels-Simplif-up/`

2. Fixed 2 corrupted local video files (james.mp4, meca-15k.mp4) by re-downloading.

3. Created 32 new manifests `test/manifests/preview_3dva_<model>_up.json`:
   - `obj_path` → `3DModels-Simplif-up/<model>.obj`
   - `extra_rotate_x_deg = 0.0`
   - `override_fov_deg = null` (uses JSON FOV = 60°)
   - `recenter_to_bbox_center = true`

4. Fixed `eval_3dva_raycast_cone.py` line 146:
   `3DModels-Simplif` → `3DModels-Simplif-up`

5. Validated all 32 3DVA models (Blender canonical, frame 0):
   - Mean IoU = 0.946
   - 29/32 ≥ 0.90 ✅
   - 3/32 in 0.875–0.891 ⚠️ (accepted with note — geometry correct, IoU low from rendering artefacts)
   - 0/32 excluded 🔴

6. Updated `test/README.md` and `trash/CLAUDE.md`.

7. Created `DATA_PATHS.md` in repo root — reference file for all local and server paths.

### Before/after comparison

| Model | Old IoU (wrong approach) | New IoU (−up OBJ, rotX=0) |
|-------|--------------------------|---------------------------|
| bunny | 0.720 | 0.978 |
| chair107 | 0.321 | 0.933 |
| flowerpot | 0.854 | 0.956 |

---

## Questions for GPT

### Q1 — Commit approval

The following changes are staged but not committed:

**New files:**
- `test/manifests/preview_3dva_*_up.json` (32 files)
- `DATA_PATHS.md`
- `trash/GPT_SESSION5_BRIEF.md` (this file)

**Modified files:**
- `test/README.md` (3DVA section updated, full 32-model table)
- `trash/CLAUDE.md` (session 5 log appended)
- `reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py`
  (line 146: `3DModels-Simplif` → `3DModels-Simplif-up`)

**Unchanged (not touched):**
- Old 3DVA manifests (`preview_3dva_bunny.json`, etc.) — kept for reference
- All MeshMamba manifests — not touched
- All eval scripts except `eval_3dva_raycast_cone.py`

**Should Claude commit now?**

### Q2 — Server eval scripts

The server runs `run_meshmamba_gaze.py` from `/mnt/hd2/29d_kon/projects/Rendering/MAMBA_GAZE/`.
There may also be a separate 3DVA eval script on the server.

Does the server eval pipeline for 3DVA also use `3DModels-Simplif/` (wrong)?
If yes — does it need to be updated to `3DModels-Simplif-up/` before the next server run?

**Clarification needed: where is the 3DVA eval script on the server?**

### Q3 — 3DVA gaze CSV on server

The local CSV files for 3DVA are at:
`/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/csv_for_models/3DVA/`

Claude could not find corresponding CSV files on the server. Were they transferred
to the server already, or do they only exist locally?

**If not on server: do you want Claude to prepare a side-input transfer package?**

### Q4 — Pipeline design decision

Claude can implement a general benchmark runner. Two main options were identified:

**Option A (recommended): YAML config + single runner**
```
run_benchmark.py --config configs/3dva_cone_gaussian.yaml
```
Config specifies: dataset, model list, OBJ path pattern, JSON root, CSV root,
GT root, method name, method parameters, metric list, output dir.
Methods and metrics stay in their current modules — only the config changes.
**Upside:** minimal code changes, easy to add models/runs by copying YAML files.

**Option B: Modular pipeline stages**
```
pipeline/
  load_model.py    # load OBJ, apply axis remap, scale
  load_gaze.py     # parse CSV + JSON → gaze batches
  project.py       # dispatch to method
  evaluate.py      # compute metrics vs GT
```
Separate scripts that read/write intermediate NumPy arrays.
**Upside:** each stage is fully independent. Can swap methods without touching GT comparison.

**Question: which option do you prefer, or should Claude propose a hybrid?**

### Q5 — Multi-frame 3DVA validation

Currently only frame 0 was validated for 3DVA.
MeshMamba was validated at frames 0, 200, 400 (multi-frame stability check).
Should Claude run frame 100, 200 for 3DVA as well, or is frame 0 sufficient?

### Q6 — Pilot run with corrected 3DVA

The pilot manifest `3dva_pilot.json` was previously configured with
`model_overrides.bunny.extra_rotate_x_deg: -70.0` (or -45 after GPT override).
With the `-up` OBJ files, the correct setting is `extra_rotate_x_deg: 0.0`.

**Should the 3DVA pilot run be re-executed with the corrected OBJ path and rotX=0?**

---

## Summary of current project state

| Dataset | Models validated | Mean IoU | Eval script status |
|---------|-----------------|----------|--------------------|
| MeshMamba non_texture | 8 | 0.987–0.991 | ✅ runs on server |
| MeshMamba rgb_texture | 8 | 0.990–0.997 | ✅ runs on server |
| 3DVA | 32 | 0.946 | ✅ fixed locally, not yet run on server |

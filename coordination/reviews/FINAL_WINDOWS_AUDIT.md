# Final Windows Agent Audit — agent/windows-video-overlays-rc3
**Gate 1: Audit & Report  (no fixes applied)**

Date: 2026-06-12  
Branch: `agent/windows-video-overlays-rc3`  
HEAD: `4ee7e58`  
Auditor: Windows Claude (independent, no prior session context re-imported)

---

## Test Results

| Check | Result |
|---|---|
| `pytest test/ tests/` | **498 passed, 0 failed, 0 errors** (12.15s) |
| `py_compile` all audit-zone files | **ALL OK** |
| `git diff --check HEAD` | **OK** (no whitespace errors) |

---

## Findings by Severity

### HIGH

#### H1 — `resolve_obj_path` for MeshMamba always returns `None` (six-view renderer)

**File:** `visualization/heatmap_six_view/render_six_view_heatmaps.py:201–208`

```python
def resolve_obj_path(dataset, dataset_root, model, texture_type):
    if dataset == "meshmamba":
        mesh_dir = dataset_root / "MeshFile" / texture_type
        return _find_file_casefold(mesh_dir, model, ".obj")   # BUG
```

`_find_file_casefold` iterates entries of `MeshFile/{texture_type}/` and looks for a
file named `{model}.obj` — but the actual on-disk layout is
`MeshFile/{texture_type}/{model}/{obj_stem}.obj` (model subdir).  
`directory.iterdir()` yields subdirectory names, not OBJ files, so this returns `None`
for every MeshMamba model.

**Impact:** Every call to `process_model` for MeshMamba with `resolve_obj_path` will
return `{"status": "error", "error_message": "OBJ not found for model '...'"}`. Renders
succeed today only because callers pass `--dataset-root` and the code hits the
`if obj_path is None` guard without crashing. Any batch run that relies on auto-resolve
silently skips all MeshMamba models.

**Reference fix pattern:** `check_alignment.py:497–527` (`_find_obj`) and
`render_batch_gt_cone.py:69` (`mesh_dir.glob("*.obj")`) both handle the nested subdir.

---

### MEDIUM

#### M1 — `auto_resolve_obj` for MeshMamba (same pattern, latent)

**File:** `video_creation/heatmap_on_mesh_video/render_heatmap_video.py:194–196`

```python
elif ds == "meshmamba":
    candidate = _casefold_find(dataset_root / "MeshFile" / texture_type, model, ".obj")
```

Same flat-directory assumption. Latent: only triggered when `--dataset-root` is
provided without `--mesh`. All production invocations (batch runners, CLI examples) pass
`--mesh` explicitly, so the latent path is never hit. Still a correctness issue for any
consumer building on this function.

---

#### M2 — Hardcoded machine-specific paths in batch runner (non-portable)

**File:** `video_creation/heatmap_on_mesh_video/render_batch_gt_cone.py:42–48, 147–148`

```python
MM_MESH   = Path("/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile")   # line 42
MM_GT_DIR = Path("/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap") # line 43
SAL_GT    = Path("/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt") # line 44
SAL_MESH  = Path("/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes")         # line 45
...
ap.add_argument("--output-dir", default="/mnt/c/Users/Danya/Downloads/...") # line 147
ap.add_argument("--cone-maps-root", default="/mnt/f/ClaudeCode/rc3_cone_maps") # line 148
```

These are Windows-WSL paths hardcoded at module level — not CLI-overridable (except
output-dir and cone-maps-root which have defaults). `MM_MESH`, `MM_GT_DIR`, `SAL_GT`,
`SAL_MESH` are only overridable by editing source. `dry_run_top20_by_cc.py:27–42`
has the same issue but explicitly documents "edit if your drives are mounted differently".
`render_batch_gt_cone.py` does not.

---

#### M3 — `check_alignment.py` uses rc2 timing (CROP_START=54); mismatch with rc3 renders

**File:** `validation/alignment_preview/check_alignment.py:88, 584`

```python
CROP_START = 54   # round(1.8 * 30)
...
placement_idx = CROP_START + gaze_k   # frame 54+k in placement JSON
```

The alignment tool was designed to validate renders under the rc2 timing contract
(crop_start=1.8s → frame 54). The new `render_heatmap_video.py` uses `rc3_one_turn`
(start=0). If a reviewer runs `check_alignment.py` to validate rc3 heatmap videos,
they will be checking frame 54+k rather than frame 0+k. Silhouette and IoU results
will be shifted 54 frames from the rendered output.

**Bounds safety:** All PREVIEW_K values are within placement JSON length
(`max placement_idx` = 54+659 = 713 < 720 for SAL3D). The existing guard at line 594
(`if placement_idx >= len(frames_list)`) prevents crashes. But the alignment result
does not correspond to frame 0 of rc3 renders.

**Note:** The tool docstring says "gaze index k → placement / video frame index
(crop_start + k)". This is internally consistent for rc2. The mismatch is only
a problem if the tool is used to validate rc3 renders. No code fix is strictly needed;
a `--timing-contract` flag or docstring clarification would resolve it.

---

### LOW

#### L1 — `probe_gpu_backend()`: vtkRenderer not added to RenderWindow

**File:** `video_creation/heatmap_on_mesh_video/render_heatmap_video.py:538–539`

```python
rw = _vtk.vtkRenderWindow()
rw.SetOffScreenRendering(1)
rw.Initialize()
_vtk.vtkRenderer()   # created but never added to rw
rw.Render()
```

`_vtk.vtkRenderer()` is immediately discarded (not `rw.AddRenderer(...)`). VTK's
`Render()` with no attached renderer is a no-op for rendering, but the GL context is
established by `Initialize()` and the ctypes GL-string query runs independently of any
renderer. In practice the GL strings are obtained correctly (confirmed by working
GPU detection in field use). The technically correct call is
`rw.AddRenderer(_vtk.vtkRenderer())`.  
Severity is LOW because the function contract (detect GPU/CPU backend) is satisfied
and all tests pass.

---

### INFO (no fix required)

#### I1 — Two audit-spec files are untracked and cannot be reviewed

`compare_processed_timing_preview.py` and
`video_creation/gaze_heatmap_overlays/render_participant_marker_overlay.py`
are listed as **untracked** in `coordination/RESTRUCTURING_REVIEW_2026-06-10.md:147–148`.
They are not committed to any branch and cannot be reviewed. Their target
classification is documented: `debug_projection/` and `video_overlays/` respectively
in the future `mesh-saliency-tools` submodule.

The audit-spec concern about `render_participant_marker_overlay.py` reading
`row["id"]` from an optional CSV column — this cannot be verified without source.
The macOS-branch legacy `render_heatmap_overlay.py` uses `row["participation_id"]`
(correct for its CSV schema); no `row["id"]` issue found in any committed code.

#### I2 — Display normalization is definitively isolated from metric computation

Both renderers separate display and metric values:

- `compute_rgb_colors` (`render_heatmap_video.py:339–379`): input `values` are never
  modified; normalization produces a new `normalized` array; `test_norm_stats_do_not_modify_input_values` verifies this explicitly.
- `load_and_prepare_map` (`render_six_view_heatmaps.py:118–174`): `values01` is a new
  array; `face_vals` is unchanged; `input_min`/`input_max` reflect pre-clip raw values.
- The `display_percentile` (p99) clip introduced in `4ee7e58` affects only the
  colormap stretch; raw min/max are still recorded in manifests as `input_min`/`input_max`.

No metric computation path reads back from any display array.

#### I3 — `check_alignment.py` placement_idx bounds are safe for all current PREVIEW_K

Max `placement_idx` = 54 + 449 = 503 for 17s datasets (510 frames total).
Max `placement_idx` = 54 + 659 = 713 for SAL3D (720 frames). Both within JSON length.
Guard at line 594 handles any future edge case.

#### I4 — `render_heatmap_overlay.py` (macOS branch, legacy CSV tool)

`origin/agent/macos-fixation-format-v2` contains an older `render_heatmap_overlay.py`
that reads participant data from a CSV via pandas (`row["participation_id"]`). This
tool was superseded by `render_fixation_overlay.py` (JSON-format, rc3). The old
file uses `ffprobe` subprocess instead of PyAV. No issue in committed code on this branch.

#### I5 — `render_six_view_heatmaps.py` GT alias fix (p99 + gt_lookup) is correct

`4ee7e58` added `display_percentile` and `gt_lookup` parameters, connected them
through `parse_args → main → process_model → load_and_prepare_map /
resolve_map_paths`. All 38 tests pass including 3 new tests covering these paths.
The fix is correct and complete.

---

## Display Normalization — Metric Computation Independence Proof

| Location | Input variable | Display variable | Metric touched? |
|---|---|---|---|
| `compute_rgb_colors` (heatmap video) | `values` (untouched) | `normalized` (new array) | No |
| `load_and_prepare_map` (six-view) | `face_vals` (untouched) | `values01` (new array) | No |
| `norm_stats` / manifest | `input_min`, `input_max` | — | Recorded only, not fed back |

---

## Camera and Transform Order Audit

| Dataset | Extra rotX | Order | Source | Matches evaluator? |
|---|---|---|---|---|
| 3DVA | 0° | scale → rotZ(frame) → +location | `_DATASET_EXTRA_ROTATE_X["3dva"] = 0.0` | ✓ (`eval_3dva_raycast_cone` default=0°) |
| MeshMamba | 90° | recenter → scale → rotX(90°) → rotZ(frame) → +location | `_DATASET_EXTRA_ROTATE_X["meshmamba"] = 90.0` | ✓ (`eval_meshmamba_cone` default=90°) |
| SAL3D | 90° | recenter → scale → rotX(90°) → rotZ(frame) → +location | `_DATASET_EXTRA_ROTATE_X["sal3d"] = 90.0` | ✓ (`eval_sal3d_cone` default=90°) |

`check_alignment.py` uses `DATASET_CONFIGS` which specifies the same per-dataset values
(`extra_rotate_x_deg: 90.0` for MeshMamba and SAL3D, `0.0` for 3DVA) and the same
`blender_rig` vs `3dva` transform_order enum.

---

## GPU Preflight Guard

| Concern | Status |
|---|---|
| nvidia-smi available check | ✓ — `probe_gpu_backend()` tries subprocess; handles exception |
| CPU fallback detection | ✓ — `_CPU_RENDERER_PATTERNS` includes llvmpipe/softpipe/mesa software/virtualbox/vmware |
| CPU frame cap (30 frames) | ✓ — `_CPU_FALLBACK_MAX_FRAMES = 30` enforced in main |
| GPU smoke cap (120 frames) | ✓ — applied unless `--full-turn` or `--allow-full-batch` |
| GALLIUM_DRIVER steering | ✓ — set before VTK init if GPU detected |
| Test coverage | ✓ — `TestGpuPreflight` (7 tests) in `test_heatmap_video_renderer.py` |
| L1 bug (vtkRenderer not added) | See L1 above — does not affect detection correctness |

---

## Jukebox GT / p99 Display (Phase 6 Changes)

| Change | File | Verified |
|---|---|---|
| `gt_lookup` param in `resolve_map_paths` | `render_six_view_heatmaps.py:211–264` | ✓ loaded from long CSV cone/ok rows |
| `display_percentile` param in `load_and_prepare_map` | `render_six_view_heatmaps.py:118–174` | ✓ clips at np.percentile; falls back to input_max if degenerate |
| `--display-percentile` CLI flag | `render_six_view_heatmaps.py:639–643` | ✓ default 100.0 (true minmax) |
| `--gt-lookup-csv` CLI flag | `render_six_view_heatmaps.py:643–648` | ✓ meshmamba-only guard |
| `display_normalization` field in manifest | `render_six_view_heatmaps.py:518–521` | ✓ "minmax_per_map" vs "percentile_{n}_display" |
| 3 new tests | `test/test_six_view_heatmaps.py` | ✓ all pass |

---

## Submodule Transfer Map (Mesh-Saliency-Tools)

Source: `coordination/RESTRUCTURING_REVIEW_2026-06-10.md`

| Current path | Future target in `mesh-saliency-tools` |
|---|---|
| `gt_visualizations/` | `heatmaps/` |
| `test/blender_canonical/` | `render_reference/` |
| `test/overlay_alignment/` | `alignment/` |
| `test/tools/` | `debug_projection/` |
| `validation/alignment_preview/` | `alignment/` |
| `video_creation/` | `video_overlays/` |
| `visualization/` | `heatmaps/` |
| `test/kld_parameter_sweep/` | **STAY in production tree** (sigma sweep driver) |

### Hard references requiring update before any physical move

| Reference file | Points to |
|---|---|
| `test/launch/run_preview_manifest.sh` | `test/tools/render_preview_from_manifest.py` |
| `test/launch/run_saliency3d_clear_pilot.sh` | `video_creation/transfer_visualizations/make_transfer_visualizations.py` |
| `reprojection_methods/.../eval_3dva_cone_combined.py` | doc ref to validation/ |
| `reprojection_methods/.../eval_3dva_raycast_cone.py` | doc ref to validation/ |
| `validation/alignment_preview/check_alignment.py` | doc/import ref to reprojection_methods |
| `visualization/heatmap_six_view/render_six_view_heatmaps.py` | doc ref |

---

## Hardcoded Path Inventory

| File | Line | Path | Overridable? |
|---|---|---|---|
| `render_batch_gt_cone.py` | 42 | `/mnt/f/ClaudeCode/MeshMamba-main/dataset/MeshFile` | Source edit only |
| `render_batch_gt_cone.py` | 43 | `/mnt/f/ClaudeCode/MeshMamba-main/dataset/SaliencyMap` | Source edit only |
| `render_batch_gt_cone.py` | 44 | `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/sal3d_fixed_face_gt` | Source edit only |
| `render_batch_gt_cone.py` | 45 | `/mnt/f/ClaudeCode/sal3d_benchmark_pkg/Meshes` | Source edit only |
| `render_batch_gt_cone.py` | 147 | `/mnt/c/Users/Danya/Downloads/...` | `--output-dir` default |
| `render_batch_gt_cone.py` | 148 | `/mnt/f/ClaudeCode/rc3_cone_maps` | `--cone-maps-root` default |
| `dry_run_top20_by_cc.py` | 27–28 | `/mnt/f/ClaudeCode/...` | Module-level (documented) |
| `dry_run_top20_by_cc.py` | 42 | `/mnt/f/ClaudeCode/rc3_cone_maps` | Module-level (documented) |
| `test/kld_parameter_sweep/run_kld_postprocess_diagnostics.py` | 36–42 | `/home/29d_kon@lab.graphicon.ru/...` | Server script, intentional |

---

## macOS Branch Independent Review

**Branch examined:** `origin/agent/macos-fixation-format-v2`

Issues found in macOS-branch-only code:

1. `video_creation/gaze_heatmap_overlays/render_heatmap_overlay.py` — legacy CSV tool.
   Uses `ffprobe` subprocess (not PyAV), `pandas`, `row["participation_id"]`.
   This is the old rc2-format reader, superseded by `render_fixation_overlay.py`.
   No `row["id"]` KeyError risk since the column name is `participation_id`.
   **Status:** Legacy/superseded, not in critical path.

2. `utils/participant_loader.py` (macOS branch) — robust, well-tested. Uses
   `CROP_START_SECONDS = 1.8`, `CROP_END_SECONDS = 0.2` (rc2 constants), matching
   the canonical evaluator contract at the time of writing.

No crashes, logic errors, or data corruption issues found in macOS branch core code
that would block merge. The macOS branch diverges primarily on evaluator migration
(processed fixation JSON format) and data organization tooling.

---

## Summary

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 1 | H1 |
| MEDIUM | 3 | M1, M2, M3 |
| LOW | 1 | L1 |
| INFO | 5 | I1–I5 |

---

## Gate 2 — Fixes Applied (2026-06-12)

All visualization/rendering/tools findings resolved. Core evaluator/runner/release code
unchanged. 537 tests pass (498 before Gate 2 + 39 new regression tests).

| Finding | Status | Change |
|---|---|---|
| **H1** | FIXED | `render_six_view_heatmaps.py`: added `_find_obj_nested` + `_normalise_lookup_name`; `resolve_obj_path` for meshmamba now handles nested `MeshFile/{tt}/{model}/{obj}.obj` layout |
| **M1** | FIXED | `render_heatmap_video.py`: added `_casefold_find_nested`; `auto_resolve_obj` meshmamba branch uses nested lookup |
| **M2** | FIXED | `render_batch_gt_cone.py`: removed module-level hardcoded paths; added `--mm-dataset-root` / `--sal3d-dataset-root` CLI flags + `MM_DATASET_ROOT` / `SAL3D_DATASET_ROOT` env vars; preflight error on missing roots |
| **M3** | FIXED | `check_alignment.py`: added `--timing-contract {rc3_one_turn,rc2_cropped}` (default: `rc3_one_turn`); `process_frame` / `process_model` accept `timing_start`; manifest records `timing_contract` + `timing_crop_start` |
| **L1** | FIXED | `render_heatmap_video.py:probe_gpu_backend`: `rw.AddRenderer(_vtk.vtkRenderer())` — renderer now attached to window before Render() |
| **I1** | SKIPPED | `compare_processed_timing_preview.py` / `render_participant_marker_overlay.py` not found locally; cannot confirm source and currency — no files added |

### Regression Tests Added

| Test file | New tests | Coverage |
|---|---|---|
| `test/test_six_view_heatmaps.py` | 17 | H1: `_find_obj_nested`, `_normalise_lookup_name`, `resolve_obj_path` MeshMamba nested |
| `test/test_heatmap_video_renderer.py` | 13 | M1: `_casefold_find_nested`, `auto_resolve_obj` nested layout |
| `test/test_alignment_preview.py` | 9 | M3: `--timing-contract` CLI default, rc3/rc2 placement_idx, bounds safety |

### Submodule Transfer Map (unchanged — no physical moves)

See [Submodule Transfer Map](#submodule-transfer-map-mesh-saliency-tools) section above.
Hard references that would break on physical move remain as documented in Gate 1.

### Remaining Blockers

None for visualization/tools scope. Untracked tools (I1) require separate source
confirmation before they can be reviewed or added.

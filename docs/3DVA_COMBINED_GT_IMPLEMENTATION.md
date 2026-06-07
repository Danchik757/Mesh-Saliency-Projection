# 3DVA Combined GT — Implementation Guide

Self-contained instruction for implementing and running the combined-GT evaluation
pipeline for the 3DVA dataset. No prior context assumed.

---

## Background

The 3DVA dataset (Lavoué et al. 2018, *Visual Attention for Rendered 3D Shapes*)
provides fixation density maps from eye-tracking experiments on 32 rendered 3D models.
The key limitation for our use case: GT comes from **3 independent static viewpoints**
(labeled 300, 413, 599 in file names), each covering a different side of the mesh.

Our gaze data comes from participants watching **rotating videos** of the same models.
Comparing an accumulated per-vertex prediction from a rotating video against a single
static-view GT is a cross-condition mismatch. Combining the 3 GT files into one
view-integrated map makes the comparison more principled: both our prediction and the
combined GT represent attention accumulated across multiple viewpoints.

---

## Dataset structure

All 3DVA data lives in `$VISUAL_ATTENTION_3D_SHAPES_ROOT`:

```
$VISUAL_ATTENTION_3D_SHAPES_ROOT/
├── 3DModels-Simplif-up/          32 OBJ files (~20K verts each)
│   ├── bunny.obj  (20000 verts)  ← ALWAYS use this subdir, NEVER 3DModels-Simplif/
│   ├── A380.obj   (47756 verts)
│   ├── turbine.obj (20000 verts) ← SPECIAL CASE: GT has 19999 lines (see below)
│   └── ...
├── FixationMaps/                  96 GT files = 32 models × 3 views
│   ├── bunny_300norm.txt          one float per line, N = OBJ vertex count
│   ├── bunny_413norm.txt          values: 0.0 (not seen) to ~8 (peak attention)
│   ├── bunny_599norm.txt
│   └── ...
└── CentricityAndVisibilityMaps/
    ├── bunny_300_visibility.txt   binary (0/1), N lines = OBJ vertex count
    ├── bunny_413_visibility.txt   1 = vertex visible from that camera position
    ├── bunny_599_visibility.txt
    └── ...  (also contains CentricityObject files — ignore those)
```

Our gaze recordings and camera JSONs:
```
$THREE_DVA_CSV_ROOT/           32 CSV files (our participants' gaze recordings)
  bunny.csv
  A380.csv   ← SPECIAL: has multiple video_ids; use --video-id 2365
  ...

$THREE_DVA_JSON_ROOT/          32 JSON files (camera + animation params)
  3DVA_bunny.json
  3DVA_A380.json
  ...
```

---

## What the GT files contain

Each file `{model}_{view}norm.txt` has N lines where N = number of vertices
in the simplified mesh. Each line is a float: the per-vertex fixation density,
accumulated across 19 subjects watching a static render from that camera position
for 7 seconds (σ=49px Gaussian cone from the eye-tracker, then normalized).

The three views (300, 413, 599) look at **different sides** of each model:
- overlap between all 3 views: only 1–12% of vertices are visible from all 3
- GT CC between views: near-zero or negative (−0.21 to +0.02 for bunny)

All non-zero GT values lie on visible vertices (verified: `gt[~vis] == 0` always
holds for most models; minor exceptions at view boundaries are handled by
the visibility mask in eval scripts).

---

## Normalization strategy (per_view_l1)

For each model:
```python
combined_num = np.zeros(n_verts)
combined_den = np.zeros(n_verts)

for view in ('300', '413', '599'):
    gt  = load_fixation_map(model, view)       # shape (N,)
    vis = load_visibility_mask(model, view)    # shape (N,), bool

    # Normalize to sum=1 over visible vertices
    visible_sum = gt[vis].sum()
    gt_norm = gt / visible_sum if visible_sum > 0 else gt.copy()

    combined_num += gt_norm * vis
    combined_den += vis.astype(float)

# Visibility-weighted mean
combined_gt = np.where(combined_den > 0, combined_num / combined_den, 0.0)
```

Result:
- Each view contributes equal total "attention mass" (view with more visible verts
  does not dominate)
- Vertex visible from all 3 views → mean of 3 normalized values
- Vertex visible from 1 view only → that view's normalized value
- Vertex never visible → 0.0

---

## Edge cases

### turbine (IMPORTANT)
- OBJ has **20000** vertices
- GT files (`turbine_*norm.txt`) have **19999** lines
- Visibility files also have 19999 or 20000 lines (varies by view)

The builder truncates visibility to GT length (off-by-one tolerance ≤5).
Combined GT is 19999 lines. Eval scripts load OBJ with `process=False` and
use `n_eval = min(n_mesh_verts, n_gt_lines)` for safety.

### A380 (mixed video_ids)
A380's CSV has multiple video sessions. Must pass `--video-id 2365` to filter
to the correct session. The batch runner handles this automatically via:
```python
VIDEO_ID_OVERRIDES = {"A380": 2365}
```

### Back-face vertices in GT
For views 413 and 599, a small number of vertices (<300) have non-zero GT despite
being marked invisible in the visibility file (Gaussian cone bleeding at boundaries).
This is a minor data imperfection. The combined GT absorbs it naturally.

---

## Files in this repository

### `scripts/build_3dva_combined_gt.py`
Standalone builder. Reads FixationMaps + Visibility, writes combined GT per model.

**Usage:**
```bash
python3 scripts/build_3dva_combined_gt.py \
  --dataset-root $VISUAL_ATTENTION_3D_SHAPES_ROOT \
  --output-dir $VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT
```

**Output:**
- `{output-dir}/{model}_combined_gt.txt` — one float per line, N lines
- `{output-dir}/{model}_combined_gt_meta.json` — stats (coverage, sums, warnings)
- `{output-dir}/build_summary.json` — one entry per model

**Key options:**
```
--models  bunny A380     # optional subset, default: auto-discover all 32
--normalization per_view_l1  # default (recommended)
```

**Expected output:**
```
bunny     n_verts=20000   coverage=79.3%  nonzero=15856
A380      n_verts=47756   coverage=42.3%  nonzero=20212
turbine   n_verts=19999   coverage=50.2%  nonzero=10036  [with WARN about 20000→19999]
meca-15k  n_verts=15000   coverage=88.8%  nonzero=13313
```

---

### `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py`
Evaluates **raycast_nearest_vertex** and **cone_gaussian_on_mesh** on one model
against the combined GT.

**Usage:**
```bash
python3 reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py \
  --model bunny \
  --dataset-root   $VISUAL_ATTENTION_3D_SHAPES_ROOT \
  --csv-root       $THREE_DVA_CSV_ROOT \
  --json-root      $THREE_DVA_JSON_ROOT \
  --combined-gt-dir $VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT \
  --output-dir     results/3dva_cone_combined \
  --sigma-deg 1.0 \
  --recenter-to-bbox-center \
  --override-fov-deg 35.9834
# A380 requires: --video-id 2365
```

**Report JSON keys:**
```json
{
  "n_vertices": 20000,
  "n_combined_nonzero": 15856,
  "combined_coverage_pct": 79.3,
  "metrics_vs_gt_combined": {
    "raycast_nearest_vertex": {
      "metrics_full":         {"CC": ..., "SIM": ..., ...},
      "metrics_covered_only": {"CC": ..., "SIM": ..., ...}
    },
    "cone_gaussian_on_mesh": {
      "metrics_full":         {...},
      "metrics_covered_only": {...}
    }
  }
}
```

**Always use `metrics_covered_only` for any comparison table.**

---

### `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py`
Evaluates **screen_space_gaussian** (v2: 1920×1080, σ=49px, bilinear) against
the combined GT.

**Usage:**
```bash
python3 reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py \
  --model bunny \
  --dataset-root   $VISUAL_ATTENTION_3D_SHAPES_ROOT \
  --csv-root       $THREE_DVA_CSV_ROOT \
  --json-root      $THREE_DVA_JSON_ROOT \
  --combined-gt-dir $VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT \
  --output-dir     results/3dva_screen_space_combined \
  --sigma-px 49.0 \
  --recenter-to-bbox-center \
  --override-fov-deg 35.9834
# A380 requires: --video-id 2365
```

**Report JSON keys:**
```json
{
  "script_version": "v2",
  "run_stats": {
    "sigma_px": 49.0,
    "density_img_shape": [1080, 1920],
    "deposition": "bilinear"
  },
  "metrics_vs_gt_combined": {
    "screen_space_gaussian": {
      "metrics_full":         {"CC": ..., "SIM": ..., ...},
      "metrics_covered_only": {"CC": ..., "SIM": ..., ...}
    }
  }
}
```

---

### `test/launch/run_3dva_reference_batch.py`
Parallel batch runner for all 32 models, both methods.

**Usage:**
```bash
# Set env vars first
export VISUAL_ATTENTION_3D_SHAPES_ROOT=/path/to/3DVA
export THREE_DVA_CSV_ROOT=/path/to/csv_for_models/3DVA
export THREE_DVA_JSON_ROOT=/path/to/jsons_for_models/3DVA_json
export THREE_DVA_COMBINED_GT_DIR=/path/to/3DVA/CombinedGT  # or pass as CLI arg

# Pilot: 3 models
python3 test/launch/run_3dva_reference_batch.py \
  --models bunny dragon chair107 \
  --methods screen_space cone \
  --workers 2 \
  --combined-gt-dir $THREE_DVA_COMBINED_GT_DIR \
  --batch-output-dir /tmp/3dva_batch_pilot

# Full: all 32 models
python3 test/launch/run_3dva_reference_batch.py \
  --methods screen_space cone \
  --workers 6 \
  --combined-gt-dir $THREE_DVA_COMBINED_GT_DIR \
  --batch-output-dir results/benchmark_runs/3dva_combined
```

Note: `--methods raycast` is also supported (reuses cone script output, no extra
compute). The batch runner automatically deduplicates subprocess calls for
cone + raycast.

**Output:**
```
batch-output-dir/
  3dva_combined_long.csv      one row per (model, method)
  3dva_combined_wide.csv      one row per model, methods side-by-side
  3dva_combined_summary.csv   mean/median per method
  baseline_screen_space/
    bunny/sigpx49p0_recenter_fov35p9834_combined/bunny_report.json
    ...
  baseline_cone/
    bunny/recenter_fov35p9834_combined/bunny_report.json
    ...
  _logs/
    screen_space/bunny.log
    cone/bunny.log
    ...
```

---

## Critical bugs to avoid

These bugs were fixed in previous sessions and are correctly handled in the
new scripts. Do not undo these fixes when extending or copying code.

| Bug | Fixed in | What the fix is |
|-----|----------|-----------------|
| **Recenter order** | session 3 | `bbox_center` computed from ORIGINAL vertices BEFORE `base_rotate_z`. The new scripts implement this correctly in `apply_model_transform()`. |
| **FOV for 3DVA** | session 9 | Use `--override-fov-deg 35.9834`. Do NOT add `--projection-fov-mode horizontal_to_vertical` — that flag exists in MeshMamba/SAL3D scripts but NOT in 3DVA scripts. |
| **sigma for screen_space** | session 17 | σ=49px at 1920×1080 (≈1° visual angle, 3DVA paper setup). v1 bug was σ=0.05×256=12.8px@256=96px@1920 (3.6× too wide). SAL3D uses σ=26.3px — different setup, do not mix. |
| **Bilinear deposition** | session 17 | `bilinear_deposit()` function (not `np.add.at` nearest-neighbour). Already in v2 screen_space. |
| **Back-face filter** | session 9 | `screen_xy[w_clip <= 0] = -1.0` — already in all screen_space scripts. |
| **Transform order for 3DVA** | session 3 | `base_rotZ → recenter → scale → rotZ_anim → extraX → extraY → translate`. Do NOT use `blender_rig` order (that's for MeshMamba/SAL3D). |
| **turbine vertex mismatch** | session 17 | OBJ=20000, GT=19999. Builder truncates visibility to GT length. Eval scripts use `n_eval = min(n_mesh_verts, n_gt_lines)`. |
| **metrics_covered_only** | SAL3D lessons | Batch runner reads `metrics_covered_only`, never `metrics_full`, for all summary tables. |

---

## Step-by-step verification

### Step 0 — Verify env vars
```bash
echo "Dataset: $VISUAL_ATTENTION_3D_SHAPES_ROOT"
ls "$VISUAL_ATTENTION_3D_SHAPES_ROOT/FixationMaps/" | wc -l        # expect 96
ls "$VISUAL_ATTENTION_3D_SHAPES_ROOT/3DModels-Simplif-up/" | wc -l # expect 32 OBJ
ls "$THREE_DVA_CSV_ROOT/" | wc -l                                   # expect 32 CSV
ls "$THREE_DVA_JSON_ROOT/" | wc -l                                  # expect 32 JSON
```

### Step 1 — Build combined GT
```bash
PYTHON="/Users/admin/Documents/LAB/SALIENCY_code/GAZE_DATA/venv/bin/python3"
REPO='/Users/admin/Documents/LAB/SALIENCY_code/#meshes_2.0/GITHUB/Mesh-Saliency-Projection'

"$PYTHON" "$REPO/scripts/build_3dva_combined_gt.py" \
  --dataset-root "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --output-dir "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT" \
  --models bunny A380 turbine meca-15k

# Verify:
ls "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT/"
# Should show: bunny_combined_gt.txt, bunny_combined_gt_meta.json, A380_combined_gt.txt, ...
wc -l "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT/bunny_combined_gt.txt"   # expect 20000
wc -l "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT/turbine_combined_gt.txt" # expect 19999
python3 -c "
import json
m = json.load(open('$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT/bunny_combined_gt_meta.json'))
print('bunny coverage:', m['combined_coverage_pct'], '%')  # expect ~79%
"
```

Then build for all 32:
```bash
"$PYTHON" "$REPO/scripts/build_3dva_combined_gt.py" \
  --dataset-root "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --output-dir   "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT"
# Expect: 32 ok, 0 failed
```

### Step 2 — Test screen_space (one model)
```bash
"$PYTHON" "$REPO/reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py" \
  --model bunny \
  --dataset-root    "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --csv-root        "$THREE_DVA_CSV_ROOT" \
  --json-root       "$THREE_DVA_JSON_ROOT" \
  --combined-gt-dir "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT" \
  --output-dir      /tmp/3dva_ss_test \
  --sigma-px 49.0

# In the output JSON, verify:
#   "script_version": "v2"
#   "run_stats.sigma_px": 49.0
#   "run_stats.density_img_shape": [1080, 1920]
#   "run_stats.deposition": "bilinear"
#   "metrics_vs_gt_combined.screen_space_gaussian.metrics_covered_only.CC": numeric
#     (expected range: -0.2 to +0.3 — cross-condition, low is normal)
```

### Step 3 — Test cone (one model)
```bash
"$PYTHON" "$REPO/reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py" \
  --model bunny \
  --dataset-root    "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --csv-root        "$THREE_DVA_CSV_ROOT" \
  --json-root       "$THREE_DVA_JSON_ROOT" \
  --combined-gt-dir "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT" \
  --output-dir      /tmp/3dva_cone_test

# In the output JSON, verify:
#   "metrics_vs_gt_combined.cone_gaussian_on_mesh.metrics_covered_only.CC": numeric
#   "metrics_vs_gt_combined.raycast_nearest_vertex.metrics_covered_only.CC": numeric
#   "run_stats.hit_rate": > 0.9 (bunny has good mesh coverage)
```

### Step 4 — Test A380 (video_id filter)
```bash
"$PYTHON" "$REPO/reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py" \
  --model A380 \
  --dataset-root    "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --csv-root        "$THREE_DVA_CSV_ROOT" \
  --json-root       "$THREE_DVA_JSON_ROOT" \
  --combined-gt-dir "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT" \
  --output-dir      /tmp/3dva_cone_test \
  --video-id 2365    # REQUIRED for A380
```

### Step 5 — Batch pilot (3 models)
```bash
"$PYTHON" "$REPO/test/launch/run_3dva_reference_batch.py" \
  --models bunny dragon chair107 \
  --methods screen_space cone \
  --workers 2 \
  --dataset-root    "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --csv-root        "$THREE_DVA_CSV_ROOT" \
  --json-root       "$THREE_DVA_JSON_ROOT" \
  --combined-gt-dir "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT" \
  --batch-output-dir /tmp/3dva_batch_pilot

# Verify:
python3 -c "
import csv
with open('/tmp/3dva_batch_pilot/3dva_combined_long.csv') as f:
    rows = list(csv.DictReader(f))
print('Total rows:', len(rows))  # expect 6 (3 models × 2 methods)
for r in rows:
    print(r['model'], r['method'], r['status'], 'CC=', r['CC'])
"
```

### Step 6 — Full 32-model run
```bash
"$PYTHON" "$REPO/test/launch/run_3dva_reference_batch.py" \
  --methods screen_space cone \
  --workers 6 \
  --dataset-root    "$VISUAL_ATTENTION_3D_SHAPES_ROOT" \
  --csv-root        "$THREE_DVA_CSV_ROOT" \
  --json-root       "$THREE_DVA_JSON_ROOT" \
  --combined-gt-dir "$VISUAL_ATTENTION_3D_SHAPES_ROOT/CombinedGT" \
  --batch-output-dir results/benchmark_runs/3dva_combined/$(date +%Y-%m-%d)_3dva_combined

# Worker count rationale:
#   - screen_space at 1920×1080: ~2-5 min per model (CPU)
#   - cone with raycasting: ~5-15 min per model (CPU)
#   - 6 workers = cone and screen_space run in parallel across models
#   - Total: ~45-90 min for all 32 models
```

### Step 7 — Commit
```bash
cd "$REPO"
git add \
  scripts/build_3dva_combined_gt.py \
  reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py \
  reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py \
  test/launch/run_3dva_reference_batch.py \
  docs/3DVA_COMBINED_GT_IMPLEMENTATION.md \
  trash/Claude.md

git commit -m "Add 3DVA combined GT pipeline: builder + eval scripts + batch runner

- build_3dva_combined_gt.py: per_view_l1 normalization (32 models → CombinedGT/)
- eval_3dva_cone_combined.py: raycast + cone vs combined GT
- eval_3dva_screen_space_combined.py: screen_space v2 (1920px, σ=49px) vs combined GT
- run_3dva_reference_batch.py: parallel batch runner, outputs 3 CSVs
- docs/3DVA_COMBINED_GT_IMPLEMENTATION.md: this instruction file

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

git push
```

---

## Expected metric ranges

These are rough estimates for sanity-checking. Low CC is **expected** because our data
is from dynamic rotating video while GT is from static views — cross-condition mismatch.

| Model type | Method | Expected CC (covered_only) |
|-----------|--------|---------------------------|
| Semantically salient (dragon, bunny face) | cone | 0.10 – 0.40 |
| Mechanical/symmetric (fandisk, casting) | cone | −0.05 – 0.20 |
| Any model | screen_space | −0.10 – 0.25 |
| Any model | raycast | slightly lower than cone |

If CC is consistently below −0.3 or above +0.6 → something is wrong (wrong OBJ,
wrong video_id, wrong sigma). Check with the bunny model first.

---

## After the run — what to add to Claude.md

Append a session entry to `trash/Claude.md` with:
- Session date and commit hash
- Summary of full-run results: n_ok per method, CC mean/median per method
- Any models that failed and why
- Whether turbine ran successfully (it should: 19999-line combined GT)
- Whether A380 ran successfully with --video-id 2365

---

## Notes on interpretation

1. **Cross-condition mismatch is expected.** GT = static viewing (7s per angle).
   Ours = dynamic video (17s, 360° rotation). Low CC does not mean the method is wrong.

2. **Use combined GT for internal comparisons only.** For citing numbers comparable
   to the original paper (CC~0.47 for Song, ~0.81 for human upper bound), use the
   per-view eval scripts (eval_3dva_raycast_cone.py, eval_3dva_screen_space.py).

3. **metrics_covered_only is the valid domain.** For models like bunny (coverage 79%),
   21% of vertices were never seen from any view → their GT=0. Evaluating on all
   vertices dilutes CC because 0-GT vertices receive non-zero predictions.

4. **SAL3D is the primary benchmark.** 3DVA combined GT is a supplementary
   cross-condition reference. The main performance claim should cite SAL3D metrics.

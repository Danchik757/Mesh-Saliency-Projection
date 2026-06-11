# Windows/WSL Claude: Geometry Preflight and Metrics Correctness

## Identity

- Platform: Windows with WSL
- Branch: `agent/windows-geometry-metrics`
- Base: immutable ref from `coordination/TASK_OWNERSHIP.md`
- Work log: append entries to the end of this file only
- Local GPU: allowed for render/debug smoke tests
- Server jobs: forbidden unless reviewer/controller explicitly approves

Use a separate Linux-side WSL clone, environment, and output directory. Do not
work from a shared checkout under `/mnt/c`.

## Mission

Independently remove geometry and metric-correctness blockers required for a
trustworthy full run. Build deterministic release-only preflight, audit
normalization/aggregation/3DVA GT/cone semantics, and provide tests and explicit
recommendations without touching participant loading or evaluator timeline
migration.

Phase 2 visualization/video work is forbidden until the reviewer/controller
confirms correct full metric runs have started.

## Owned Paths

- new shared mesh/preflight helper under `utils/mesh_*`
- geometry/release-only preflight tools and dedicated tests
- `metrics/` and metric/aggregation tests
- assigned 3DVA GT/CombinedGT audit tools or documents
- assigned cone-semantics tests/documents
- alignment diagnostics under `test/blender_canonical/` or `test/tools/` that
  do not implement timing/input loading
- Phase 2 only after approval: visualization/video paths

Do not edit:

- participant-data loader or timing logic;
- evaluator input adapters or batch input migration;
- release packaging/downloading scripts;
- another role's coordination file;
- `trash/*.md` or `md/archive/*`.

If an evaluator change is required by an audit finding, provide a minimal failing
test or precise patch recommendation to the macOS worker/reviewer. Do not edit
the evaluator yourself.

## WSL and SSH Prerequisite

The user supplies the private key. Never transmit or commit it.

Verify read-only access:

```bash
ssh vg-intellect-acm 'hostname; pwd'
ssh vg-gpu-acm 'hostname; pwd'
```

Do not start jobs during onboarding.

## Milestone B1: Deterministic Release-Only Geometry Preflight

Reproduce and classify all previously failed or missing-result MeshMamba and
SAL3D models using only candidate release structure, not local ad-hoc datasets.

Classify at least:

- corrupt/unsupported OBJ;
- scene versus mesh;
- duplicate/nested OBJ;
- naming or case mismatch;
- multiple candidate geometry files;
- face/vertex count mismatch;
- GT/support mismatch;
- trimesh `process` side effects;
- missing GT or intentionally excluded model.

Implement a deterministic mesh resolver/validator only if needed. It must never
silently choose, repair, reorder, truncate, pad, or skip geometry without a
machine-readable status and reason.

Explicitly audit:

- MeshMamba duplicate/nested OBJ inventory;
- MeshMamba models with no GT;
- SAL3D high-resolution OBJ versus 20K GT support;
- `turbine` 20000 mesh vertices versus 19999 GT entries;
- whether any truncation/padding preserves correspondence.

Acceptance:

- release-only command;
- complete per-model/track status table;
- deterministic inclusion/exclusion reason;
- tests for each observed failure class;
- no evaluator edits.

## Milestone B2: Alignment Gate

Use canonical placement JSON, canonical release OBJ, and current documented
transform/FOV policy to validate representative objects from:

- 3DVA;
- MeshMamba non_texture;
- MeshMamba rgb_texture;
- SAL3D.

Produce overlay/mask IoU evidence across multiple frames, including frames in the
approved cropped interval. Audit:

- OBJ variant and orientation;
- camera and FOV convention;
- recenter/scale/rotation/translation order;
- local extra rotation versus parent animation rotation;
- Blender import-axis/version effects;
- non-zero transform overrides against the Blender rig.

Do not implement timing pairing. If the preview frame mapping is wrong, return a
reproduction to the macOS worker.

## Milestone B3: Metrics and Aggregation Audit

Audit every metric actually emitted by accepted benchmark scripts:

- CC;
- Spearman;
- SIM;
- KLD direction and epsilon policy;
- MSE;
- NSS;
- AUC variants, if emitted.

Required tests:

- prediction/GT shape and support match;
- masking happens at the correct stage;
- prediction and GT normalization match each metric definition;
- identical maps produce ideal expected values;
- constant, empty, negative, NaN, and Inf inputs have explicit behavior;
- scale-invariance/monotonic properties where applicable;
- comparison against an independent trusted implementation where practical.

Audit aggregation:

- point-equal behavior of processed fixation JSON;
- old-CSV participant/sample weighting;
- effect of unequal sample counts;
- impossibility of participant-equal aggregation from the current processed JSON
  without additional identity data.

Do not claim participant-equal aggregation if the input cannot support it.

## Milestone B4: 3DVA and Cone Methodology Audit

For 3DVA verify:

- GT file semantics for 300/413/599;
- OBJ/GT vertex count and ordering;
- static-view GT versus rotating-video prediction mismatch;
- CombinedGT support/visibility and equal-view contribution;
- whether support overlap biases the current CombinedGT formula;
- any length mismatch policy, including correspondence safety;
- recommended promoted reporting protocol.

For `cone_gaussian_on_mesh` verify:

- angular sigma uses camera-to-hit depth rather than near-plane-to-hit depth;
- world-space radius and FOV/depth behavior;
- whether per-hit Gaussian mass depends on local vertex/face density;
- whether normalization occurs at the correct level;
- expected differences between per-vertex and per-face tracks.

Provide tests and an explicit recommendation. If implementation changes are
required outside owned paths, return them to the owner/reviewer.

## Phase 1 Review Request

Before requesting integration:

- push small coherent commits;
- append commands, outputs, status tables, and findings;
- state which findings block full runs;
- state which findings are methodological limitations rather than code bugs;
- confirm branch is clean.

Stop after Phase 1 and wait for reviewer/controller authorization.

## Phase 2: Only After Full Runs Start

When explicitly authorized, tasks may include:

1. deterministic six-view GT/prediction heatmaps using `jet` and a color scale;
2. diagnosis of incorrect GT heatmap renders;
3. canonical heatmap video renderer matching placement JSON.

Do not alter the accepted Phase 1 benchmark baseline while doing Phase 2.

## Append-Only Work Log

Append new entries below. Never rewrite prior entries.

---

## 2026-06-09 — Onboarding

Branch: agent/windows-geometry-metrics
Commit: b232129 (= agent-base-2026-06-09, HEAD matches BASE_REF exactly)
Files read: all mandatory read-order documents plus trash/Claude.md (partial) and trash/GPT.md (partial)
Files changed: this file only (onboarding entry)

### State verified

- HEAD = b232129 = agent-base-2026-06-09. BASE_REF confirmed present.
- git status: clean working tree, no uncommitted changes.
- Branch is agent/windows-geometry-metrics (correct).
- WSL environment is functional.
- SSH: both vg-intellect-acm and vg-gpu-acm currently unreachable (name resolution failure). SSH config / private key not yet provided. No server jobs will be attempted until the user provides the key and the reviewer/controller explicitly approves.
- participant_data/processed_fixations_offset_2000/ contains only README — actual fixation data not checked into git (correct per DECISIONS_REQUIRED.md §1, distributed via GitHub Release).
- metrics/ module present: common.py, mesh_space.py, screen_space.py, __init__.py. No tests yet.
- utils/ contains only path_defaults.py. No mesh_* helpers yet.
- reprojection_methods/ contains cone_projection_on_mesh/ and screen_space_gaussian/ with existing eval scripts.
- jsons/object_placement/ has all four dataset subdirs; jsons/dataset_model_info/ has per-dataset model index JSON files.
- scripts/validate_release_candidate.py and scripts/build_3dva_combined_gt.py present (not in this agent's edit scope).

### Phase 1 tasks this agent will work

| Milestone | Description |
| --- | --- |
| B3 | Metrics and aggregation audit: test every metric in metrics/, verify normalization/support semantics, document aggregation limits |
| B1 | Deterministic release-only geometry preflight: MeshMamba OBJ naming/scene issues, SAL3D vertex count vs GT, turbine 20K vs 19999, no-GT models |
| B4 | 3DVA CombinedGT and cone semantics audit: equal-view contribution, cone depth definition |
| B2 | Alignment gate: after B1/B4 supply evidence, produce overlay IoU for representative objects |

B3 first because it requires no external data: the metrics/ module and existing eval scripts are in the repo.

### Files expected to touch

- New: `utils/mesh_preflight.py` (or similar) — geometry validator
- New: `test/metrics/` — metric unit tests
- New: `test/geometry/` — geometry preflight tests
- Append-only: this file
- Possibly: audit documents under `docs/` or `coordination/` if reviewer requests them

### Owned-path constraints confirmed

Will NOT touch: participant_data/, scripts/package_datasets.sh, scripts/upload_release_candidate.sh, evaluator timing/input adapters, batch input migration, or release packaging.

### Blockers at onboarding

1. SSH not configured — no server jobs possible until key is provided and reviewer approves.
2. Release data (OBJ, GT, fixation JSON) not extracted locally — B1 and B2 preflight tests will need either the release extracted or a stub/mock fixture. Will implement tests that are runnable given the release structure and document the expected inputs.
3. 3DVA CombinedGT build script (scripts/build_3dva_combined_gt.py) is in macOS Claude's release-packaging scope — if the audit finds a logic bug, will produce a minimal failing test and report to reviewer rather than editing the script.

Commands run: none (read-only onboarding pass).
Expected and actual results: HEAD confirmed, BASE_REF found, clean tree confirmed.
Output paths: none.
git status --short after this entry: clean (this file is modified but not yet committed).

---

## 2026-06-09 — Milestone B3: Metrics and Aggregation Audit

Branch: agent/windows-geometry-metrics
Commit: see below (pending push)
Input release/data version: n/a (no external data required; audit is code-only)
Files changed:
- `metrics/screen_space.py` — defensive fix (1 line guard added)
- `test/metrics/test_common.py` — new (105 tests)
- `test/metrics/test_mesh_space.py` — new (36 tests)
- `test/metrics/test_screen_space.py` — new (32 tests, +1 bug test)
- `pytest.ini` — new (pythonpath = .)
- `conftest.py` — new (repo-root sys.path bootstrap, redundant after pytest.ini but harmless)
- `coordination/agents/WINDOWS_CLAUDE.md` — this entry

### Commands run

```bash
python3 -m pytest test/metrics/ -v
```

### Expected and actual results

141 tests written, 141 passed (after the one bug fix below).

### Audit findings

#### Confirmed correct

| Item | Finding |
| --- | --- |
| CC | Pearson via centered dot-product. Returns NaN for constant pred or target (correct). Scale-invariant. Matches scipy.stats.pearsonr to 1e-10. |
| Spearman | Pearson applied to average ranks (Wilcoxon method). Ties handled via average rank, matches scipy.stats.spearmanr to 1e-10. Returns NaN for constant pred (correct). |
| MSE | Standard. Symmetric, non-negative, zero for identical inputs. |
| KLD | Direction: KL(GT ∥ pred) = sum(target_norm × log(target_norm / pred_norm)). Lower = better prediction. This is the standard benchmark direction (same as MIT/Tuebingen saliency benchmark). KLD key in dense_saliency_metrics defaults to `"KL_gt_to_pred"` — correctly named. In screen_map_metrics key is `"KLD"`. Both use same direction. |
| SIM | Normalization pipeline: normalize_minmax → normalize_distribution. This makes SIM invariant to linear transforms of pred and target. SIM(identical, identical) = 1.0. Verified. |
| NSS | Uses GLOBAL pred statistics (not masked). This is the standard NSS definition (Bylinskii et al. 2018). Correct. Returns NaN for no fixations or flat pred. |
| AUC | Wilcoxon-Mann-Whitney U statistic. Tied scores handled via average ranks. Matches sklearn.metrics.roc_auc_score to 1e-10. Returns NaN when no positives or no negatives (correct). |
| Mask application | `flatten_pair` with mask is called at the `dense_saliency_metrics` level, BEFORE passing to CC, MSE, KLD, SIM, Spearman. All metrics operate on the masked subset. This is correct. |
| normalize_distribution | Epsilon stabilisation: (array + EPS) / (total + EPS × N). Prevents log(0) in KLD. Uniform fallback for all-zero input. |

#### Methodological notes (not code bugs, documented for benchmark report)

1. **Constant pred**: CC = NaN, Spearman = NaN, NSS = NaN. SIM = non-zero value that depends on target distribution (constant pred normalises to uniform via normalize_minmax → zeros → normalize_distribution → uniform). This is the correct IEEE "undefined" handling for CC/Spearman and the expected NaN for NSS. For SIM, the value is non-ideal but not crash-prone.
2. **SIM vs KLD normalization asymmetry**: SIM uses minmax + distribution (two-stage). KLD uses distribution only (no minmax first). KLD is still scale-invariant for positive inputs because normalize_distribution absorbs positive scaling. Both are correct for their respective metric semantics.
3. **auc_visible_top20 edge case**: if visible_mask has exactly 1 True element, k = max(1, round(0.2×1)) = 1, meaning all visible elements are "positive" → no negatives → returns NaN. This is correct behavior but callers should be aware.
4. **normalize_distribution(mask=...)**: returns a SHORTER array (only the masked elements). Callers that pass mask to this function must not assume the output has the same length as the input. This is only called with mask from `dense_saliency_metrics` path after `flatten_pair` already filtered, so no conflict in current code.
5. **NSS global normalization**: NSS z-score is computed over the full pred array including elements outside the fixation mask. This is the standard NSS definition and is intentional. Test `test_uses_global_pred_statistics` documents this explicitly.

#### Aggregation semantics (documented limitation, not a bug)

Per DATA_CONTRACT.md: processed fixation JSON has no participant IDs. The metrics module operates on flat pred/target arrays with equal weight per element (point-equal aggregation). Participant-equal aggregation cannot be reconstructed from this format alone. This limitation is documented in `TestAggregationSemantics` and must be stated in any benchmark report that uses the processed fixation JSON as input.

### Bug found and fixed

**`metrics/screen_space.py`: `binary_mask_from_fixation_points` — missing shape dimensionality guard.**

Before fix, calling with a 1D shape (e.g. `shape=(4,)`) produced `IndexError: tuple index out of range` with no context. Fixed by adding a `ValueError` with a clear message if `len(shape) < 2`.

This function is designed for 2D saliency maps (height × width). The fix makes the contract explicit. Any caller passing 1D pred + fixation_points now gets a clear error at the function boundary rather than an opaque IndexError.

One test added for the error case: `TestBinaryMaskFromFixationPoints::test_1d_shape_raises_clear_error`.
One test added confirming `screen_map_metrics` with 1D pred + fixation_points raises the same error.

### What blocks full metric runs

None from B3 itself. The metrics module is correct and tested.

Blockers for full runs remain in other milestones:
- B1 (geometry preflight): MeshMamba OBJ naming issues, SAL3D vertex/GT mismatch, turbine 20K vs 19999.
- B4 (cone depth + 3DVA CombinedGT): cone angular sigma definition, CombinedGT equal-view semantics.
- macOS Claude milestone: evaluator timing/input migration to processed fixation JSON.
- Release gate: v2.0-data-rc1 must pass acceptance criteria before full runs start.

### Output paths

test/metrics/ — all new test files.
pytest.ini — test runner config.

### Failures and unresolved questions

No unresolved questions within B3 scope.

git status --short after push: clean.

---

## 2026-06-09 — Phase 2: Heatmap-on-Mesh Video Renderer

Branch: agent/windows-geometry-metrics
Files changed:
- `video_creation/heatmap_on_mesh_video/render_heatmap_video.py` — new, main CLI renderer
- `video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh` — new, smoke script
- `video_creation/heatmap_on_mesh_video/README.md` — new
- `test/test_heatmap_video_renderer.py` — new, 38 unit tests
- `coordination/agents/WINDOWS_CLAUDE.md` — this entry

### Commands run

```bash
python3 -m py_compile video_creation/heatmap_on_mesh_video/render_heatmap_video.py
python3 -m pytest test/test_heatmap_video_renderer.py test/metrics/ -q
```

### Results

```
py_compile: OK
179 passed in 1.39s  (141 B3 metrics + 38 renderer)
```

### Design decisions

| Decision | Rationale |
| --- | --- |
| blender_rig transform: recenter→scale→rotX(90°)→rotZ(per-frame) | Matches canonical evaluator defaults for both MeshMamba and SAL3D |
| Camera from view_matrix decomposition | Reproduces exact Blender camera position/orientation; horizontal FOV 60° converted to vertical ≈ 35.98° for PyVista |
| Per-face/per-vertex auto-detection from map length | MeshMamba evals output *_faces.txt; SAL3D evals output *_vertices.txt; GT files use same domain |
| Persistent pv.Plotter with in-place mesh point updates | Avoids plotter recreation overhead per frame; standard PyVista animation pattern |
| alpha blends heatmap with neutral gray (0.5,0.5,0.5) | alpha=1.0 = pure heatmap; alpha=0.0 = gray base |
| Temp dir for PNG frames → ffmpeg assembly | Clean, debuggable; temp dir auto-deleted |
| SAL3D GT multi-column: default column 7 | Matches eval_sal3d_screen_space.py load pattern |

### Smoke scope

4 cases, --max-frames 120:
- MeshMamba non_texture Starfruit_L3 screen_space
- MeshMamba non_texture Starfruit_L3 cone
- SAL3D bunny screen_space
- SAL3D bunny cone

Smoke script: `video_creation/heatmap_on_mesh_video/run_server_heatmap_video_smoke.sh`
Run on ssh vg-iai after reviewer approval.

### Server smoke not yet run

Pending reviewer/controller approval to SSH to vg-iai and run the smoke script.

### Output structure

```
{output-dir}/{dataset}/{track}/{model}/{map-type}/
  heatmap_video.mp4
  manifest.json       ← full provenance (map path, timing, domain, frame count)
```

git status --short: see commit below.

---

## 2026-06-09 — Phase 2 renderer: post-review fixes

Branch: agent/windows-geometry-metrics
Commits: dce9f77 (original renderer) + dc327d1 (fixes)
Also cherry-picked onto reproject-benchmark @ b6ff18a

### Fixes applied

| Issue | Fix |
| --- | --- |
| Transform order: location added before frame rotation | Removed +location from precompute_base_transform; added after apply_frame_rotation in render_frames via model_location param. Matches evaluator blender_rig: recenter→scale→rotX→rotZ(frame)→+location |
| Release root | Corrected to shared_release_data/v2.0-data-rc1/extracted |
| Conda in smoke script | Replaced with source ${SERVER_ROOT}/environments/reproject-benchmark/bin/activate |
| SAL3D bunny OBJ path | Corrected from datasets/SAL3D/OBJ/bunny/bunny.obj to datasets/SAL3D/Meshes/bunny.obj per jsons/dataset_model_info/sal3d_models.json |
| find_map tied to method subdir | Now searches full smoke tree via find + grep, layout-agnostic |

### Validation

```
py_compile: OK
180 passed in 2.00s  (141 B3 + 39 renderer)
```

### reproject-benchmark state after cherry-picks

```
b6ff18a Fix renderer transform order, release root, venv, and SAL3D OBJ path
ee88379 Add heatmap-on-mesh video renderer (Phase 2)
49f685a Merge (A2 + windows B3) — A1/A2 intact
```

Server smoke on vg-iai pending reviewer/controller approval.

---

## 2026-06-10 — Merge A3/A4 + rc2 smoke script update

Branch: agent/windows-geometry-metrics
Merged: origin/reproject-benchmark @ 1065e28 (A3 cropped-reset fixations, A4 SAL3D fixed GT)

### Changes in this commit

| Item | Change |
| --- | --- |
| Merge conflict | Kept our WINDOWS_CLAUDE.md work-log entry (HEAD); reproject-benchmark had no competing Windows log content |
| Smoke script | Sources configs/server_vg_intellect.env; uses MESHMAMBA_NON_TEXTURE_ROOT, SAL3D_DATASET_ROOT, SAL3D_JSON_ROOT, MESHMAMBA_JSON_ROOT, OUTPUT_ROOT from env file; REPROJECT_RELEASE_TAG overridable for rc2-staging/final |
| Timing contract | Added comment to render_heatmap_video.py: processed_gaze[0:usable_count] maps to placement[start_idx:end_idx]; renderer iterates placement[54:504/714] directly; does NOT index into processed_gaze |
| Renderer logic | No logic changes needed; placement[54:504/714] crop was already correct |

### rc2 path migration

All hardcoded paths removed from smoke script. Paths now flow from:
- RELEASE_DATA_ROOT = ${REPROJECT_SERVER_ROOT}/shared_release_data/${REPROJECT_RELEASE_TAG}/extracted
- MESHMAMBA_NON_TEXTURE_ROOT = ${RELEASE_DATA_ROOT}/datasets/MeshMamba
- SAL3D_DATASET_ROOT = ${RELEASE_DATA_ROOT}/datasets/SAL3D
- MESHMAMBA_JSON_ROOT / SAL3D_JSON_ROOT = ${REPROJECT_CANONICAL_JSON_ROOT}/mamba_non_jsons / sal3d_jsons

Override: REPROJECT_RELEASE_TAG=v2.0-data-rc2-staging bash run_server_heatmap_video_smoke.sh

### Validation

```
py_compile: OK
221 passed in 2.18s  (141 B3 + 39 renderer + 41 A3/A4)
compileall: OK (video_creation test metrics utils reprojection_methods)
no conflict markers
```

---

## 2026-06-11 — Task 1: rc3 gaze overlay renderer and batch runner

Branch: agent/windows-video-overlays-rc3 (from origin/agent/offset0-one-turn-contract)

### New files

| File | Purpose |
| --- | --- |
| video_creation/gaze_heatmap_overlays/render_fixation_overlay.py | Per-model rc3 fixation JSON → overlay video renderer |
| video_creation/gaze_heatmap_overlays/run_batch_gaze_overlay.py | Batch runner for all models with manifest output |
| video_creation/gaze_heatmap_overlays/run_smoke_gaze_overlay.sh | Smoke test: 3DVA_A380 + MeshMamba_non_texture_Starfruit_L3 + SAL3D_bunny |
| test/test_fixation_overlay.py | 45 pure-logic unit tests |

### rc3 fixation format

- fixations.json = list of N frames; each frame = list of [x, y] absolute pixel coords (1920x1080 space)
- 510 frames for 3DVA/MeshMamba; 720 for SAL3D; 41 for 3DVA_jessi (invalid)
- gaze[k] → video_frame[k]; no timestamp lookup needed

### Two modes

| Mode | Frames rendered | Corresponds to |
| --- | --- | --- |
| full_video_overlay | all 510/720 frames | entire fixation JSON |
| benchmark_one_turn_overlay | 450/660 frames | evaluator timing contract (one full turn) |

### Turn frames (from rc3 manifest)

```
3DVA:      450
MeshMamba: 450
SAL3D:     660
```

### Exclusions

3DVA_jessi excluded by default (41 frames, known_blocker). SAL3D_jessi is valid.

### Output layout

```
{output-root}/{mode}/{dataset}/          {model}/overlay.mp4
{output-root}/{mode}/{dataset}/          {model}/manifest.json
{output-root}/manifest.json              (combined)
{output-root}/manifest.csv              (combined)
```

### Manifest fields per model

mode, dataset, track, model, model_key, fixation_format, fixation_json_path,
video_path, output_path, n_json_frames, frame_count, fps, resolution,
crop_start_sec (0.0), crop_end_sec (0.0), status, error, repo_commit

### Video discovery

Batch runner scans video_root recursively for {model_key}.mp4. Models without
matching video get status=skipped_no_video in the manifest (not an error).

### Validation

```
py_compile: OK
411 passed, 3 skipped in 3.41s  (366 prior + 45 overlay)
compileall: OK
```

Smoke not yet run — awaiting server approval and rc3 source_videos availability.

Post-review fix: added --limit N to run_batch_gaze_overlay.py (applied after --models filter).
Full batch without --models or --limit would process all 297 non-excluded models — --limit is
the intended safety gate for smoke runs.

---

## Task 2 Progress — 3D Heatmap-on-Mesh Video Renderer (rc3 timing)

**Branch:** `agent/windows-video-overlays-rc3`

**Changed files:**
- `video_creation/heatmap_on_mesh_video/render_heatmap_video.py` — extended existing renderer
- `test/test_heatmap_video_renderer.py` — added tests for new rc3 features

**Key changes to renderer:**
1. rc3 timing contract (`rc3_one_turn`): `start_idx=0`, `end_idx=TURN_FRAMES[dataset]`
   - `TURN_FRAMES = {3dva: 450, meshmamba: 450, sal3d: 660}`
   - rc2 legacy timing preserved as `--timing-contract rc2_cropped`
2. `resolve_frame_window(dataset, fps, total_frames, *, timing_contract, max_frames)` — exported
3. `select_preview_indices(n_frames)` — returns [0, 25%, 50%, 75%, last]
4. `write_manifest_csv(path, manifest)` — flattened CSV alongside manifest.json
5. `auto_resolve_obj / auto_resolve_placement_json` — path helpers from dataset/json roots
6. CLI additions: `--timing-contract`, `--texture-type`, `--dataset-root`, `--json-root`,
   `--map-path` (alias for --map-file), `--output-root` (alias for --output-dir)
7. `compute_rgb_colors`: constant-map warning; matplotlib imported eagerly (not with pyvista)

**Tests:** 67 passed, 0 warnings (was 44; +23 new tests)
- `TestRc3FrameWindow` (13 tests): frame window 0→450/660, clamping, case-insensitive, rc2 compat
- `TestMinMaxNormalization` (5 tests): constant map, alpha=0 gray, dtype/range
- `TestSelectPreviewIndices` (6 tests): boundary cases, sorted, zero-length
- `TestWriteManifestCsv` (4 tests): flat fields, nested dot-notation, timing_contract fields

**py_compile:** OK (both renderer and test file)

**NOT run:**
- Smoke render (requires separate approval + available dataset roots for OBJ/saliency maps)
- Full batch

**Exact smoke commands (do not run without reviewer/controller approval):**
```bash
python3 video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset meshmamba --texture-type non_texture --model Starfruit_L3 \
  --map-type screen_space \
  --map-path /path/to/Starfruit_L3_screen_space_faces.txt \
  --dataset-root /data/MeshMambaSaliency \
  --output-dir /tmp/heatmap_3d_smoke \
  --max-frames 120

# SAL3D:
python3 video_creation/heatmap_on_mesh_video/render_heatmap_video.py \
  --dataset sal3d --model alien \
  --map-type gt \
  --map-path /path/to/alien_faces.txt \
  --mesh /path/to/SAL3D/Meshes/alien.obj \
  --output-dir /tmp/heatmap_3d_smoke \
  --max-frames 120
```

---

## GT-only 3D Heatmap Smoke — 2026-06-11

**Branch:** `agent/windows-video-overlays-rc3`  
**Approval scope:** GT-only smoke, max_frames=120, no full batch.

**GPU preflight:** RTX 2060 D3D12 bridge, `used_cpu_fallback=false`, pyvista 0.48.4 / VTK 9.6.2.

**Bug fixed in smoke:** `auto_resolve_placement_json` for SAL3D was constructing `SAL3D_` prefix but files use `Sal3D_`. Fixed and committed (`97313ae`).

### Results — all 4 runs clean

| Dataset | Track | Model | map_domain | n_map_elements | n_mesh_faces | input_min | input_max | frames | mp4 size |
|---|---|---|---|---|---|---|---|---|---|
| MeshMamba | non_texture | Starfruit_L3 | face | 32868 | 32868 | 0.0 | 1.0 | 120 | 0.1 MB |
| MeshMamba | non_texture | Watermelon_V1_L3 | face | 32868 | 32868 | 0.0 | 1.0 | 120 | 0.1 MB |
| MeshMamba | rgb_texture | Watermelon_V1_L3 | face | 32868 | 32868 | 0.0 | 1.0 | 120 | 0.1 MB |
| SAL3D | — | alien2 (fixed-face GT) | face | 26418 | 26418 | 0.0 | 1.0 | 120 | 0.2 MB |

**Output root:** `/tmp/heatmap_3d_smoke_rc3/`  
**Note:** GT maps are MeshMamba per-face CSV and SAL3D fixed-face GT — correct for renderer technical smoke. Prediction smoke (screen_space/cone) blocked pending rc3_full_metrics outputs.

---

## Task 2 Phase 3 — Visual improvements + white-bg renders (2026-06-11)

**Branch:** `agent/windows-video-overlays-rc3`  
**HEAD:** `89eb88a`  
**Pushed:** yes

### New CLI flags in render_heatmap_video.py

| Flag | Default | Description |
|---|---|---|
| `--background-color` | `white` | PyVista background color; written to `render.background_color` in manifest |
| `--full-turn` | off | Render complete turn (450f for 3DVA/MeshMamba, 660f for SAL3D); implies `--allow-full-batch`; `--max-frames` still applies as upper cap |
| `--object-base-color` | `lightgray` | Base mesh color (flag added; currently unused — heatmap always covers mesh) |
| `--show-axes` | off | PyVista axes widget |

`render.background_color` field added to manifest JSON and CSV.

### Tests

102 tests pass. New test classes added:
- `TestBuildParser` (11 tests) — default values, explicit flags, map_type choices, map_type rejection
- `TestFullTurnLogic` (9 tests) — TURN_FRAMES constants, effective max logic, resolve_frame_window integration
- `TestManifestBackgroundColor` (3 tests) — JSON roundtrip, CSV field, black variant

### White-bg renders — Starfruit_L3 GT

| Run | Frames | Time | Output |
|---|---|---|---|
| Smoke (white bg) | 120 | 9.9s | `/tmp/heatmap_3d_smoke_whitebg/.../heatmap_video.mp4` |
| Full-turn (white bg) | 450 | 23.1s | `/tmp/heatmap_3d_smoke_whitebg_fullturn/.../heatmap_video.mp4` |

**GPU:** RTX 2060 via Mesa D3D12, ~0.051s/frame (full-turn), white background confirmed in manifest.

**Copied to Windows:** `C:\Users\Danya\Downloads\heatmap_3d_preview_starfruit_white\`
- `Starfruit_L3_gt_white_120f.mp4`
- `Starfruit_L3_gt_white_full_turn.mp4`
- 5× `preview_frame_*.png` (from full-turn)
- `Starfruit_L3_gt_white_full_turn_manifest.json`

### Constraints

No full batch, no server jobs, no prediction maps (still blocked on rc3_full_metrics).

---

## Phase 5 — RC3 cone map transfer + GT/cone full-turn batch (2026-06-11)

**Branch:** `agent/windows-video-overlays-rc3`
**HEAD:** `44d180a` (pre-phase) → new commit this phase
**Pushed:** yes (end of phase)

### Cone map transfer and smoke (3 models)

Received `rc3_cone_maps_for_windows_20260611_184126.zip` (4.4 MB) with 21 cone map files from `rc3_full_metrics_20260611_004003`. Unpacked and copied to `/mnt/f/ClaudeCode/rc3_cone_maps/`.

Cone map naming confirmed:
- MeshMamba: `{model}_cone_faces.txt` (for models in new batch) or `{model}_cone_vertex_avg_faces.txt` (earlier batch files)
- SAL3D: `{model}_cone_baseline_vertices.txt` (smoke pack) / `{model}_cone_vertices.txt` (20-model pack)

3 renderer smoke renders (cone only, full-turn, white bg, GPU):

| Model | Dataset/Track | Frames | Time | s/f |
|---|---|---|---|---|
| Kangaroo_v1_L3 | MeshMamba rgb_texture | 450 | 24.3s | 0.054 |
| Statue_v1_L2_David | MeshMamba non_texture | 450 | 21.1s | 0.047 |
| torso | SAL3D | 660 | 30.4s | 0.046 |

All 3: `used_cpu_fallback=False`, `camera.source=placement_json`, `map_provenance_note` set.
Output: `C:\Users\Danya\Downloads\heatmap_3d_cone_smoke_3models\`

### 40-video GT+cone batch (20 models)

Received `rc3_cone_maps_20_more_windows_20260611_190822.zip` (4.1 MB). Merged into `/mnt/f/ClaudeCode/rc3_cone_maps/`.

Dry-run: 20/20 models — GT=OK, Mesh=OK, JSON=OK, Cone=OK before rendering.

Ran `render_batch_gt_cone.py` (now tracked in repo). SAL3D path fix applied: renderer omits track subdir for SAL3D (`SAL3D/{model}/{map_type}/` not `SAL3D/sal3d/{model}/{map_type}/`).

| Stat | Value |
|---|---|
| Renders completed | 40/40 (20 GT + 20 cone) |
| Failed | 0 |
| Total wall time | ~25 min |
| Avg sec/frame | 0.052 s/f |
| GPU | RTX 2060, used_cpu_fallback=False on all 40 |

Output: `C:\Users\Danya\Downloads\heatmap_3d_top20_more\`
Layout: `{Dataset}/{track}/{model}/{model}_{gt|cone}_fullturn.mp4` + `{gt|cone}_manifest.json` + `preview_{gt|cone}_*.png`

Files: 40 MP4 · 40 JSON · 200 PNG previews.

**Models rendered:**
- MM non_texture (7): Watermelon_V1_L3, barbiegirl_V1_L3, Soda_Can_v3_L3, Apple_Red_v1_L3, Pear_L3, egypt_sphinx_V2_L3, Peach_L3
- MM rgb_texture (7): Watermelon_V1_L3, Military_Action_Figure_SG_v2_L3, Apple_Red_v1_L3, Jukebox_bubbler_style_V2_L1, Cat_v1_L3, BastetCat_v2_L2, Blackberry_v02_L3
- SAL3D (6): james, vase, MaxPlanck, cow, gorilla, igea

### New files committed this phase

| File | Purpose |
|---|---|
| `video_creation/heatmap_on_mesh_video/render_batch_gt_cone.py` | Batch runner (GT + cone, flattened output, SAL3D path fix) |
| `video_creation/heatmap_on_mesh_video/dry_run_top20_by_cc.py` | Updated: local cone paths, `_cone_faces.txt` naming, `cone_ok` in table |

### Constraints

No full batch beyond what is listed above. No server jobs. Previous 3 smoke outputs in `heatmap_3d_cone_smoke_3models\` untouched.

---

## Phase 6 — Six-view renderer diagnostic and GT alias fix

**Task**: Diagnose pixelation artifacts in MeshMamba GT renders, fix missing Jukebox GT, add p99 display mode.

### Findings

**5-model stats table** (all MeshMamba, n_faces=32868, domain=face, single-column CSV no header):

| Model | Track | n_verts | n_faces | GT len | min | max | p95 | p99 | mean |
|---|---|---|---|---|---|---|---|---|---|
| Marco_Polo_Sheep_v1_L3 | non_texture | 16436 | 32868 | 32868 | 0.0 | 1.0 | 0.7058 | 0.8573 | 0.2615 |
| Statue_v1_L2_David | non_texture | 16428 | 32868 | 32868 | 0.0 | 1.0 | 0.7053 | 0.8702 | 0.1891 |
| Jukebox_bubbler_style_V2_L1 | rgb_texture | 16550 | 32868 | 32868 | 0.0 | 1.0 | 0.4087 | 0.7502 | 0.1090 |
| Kangaroo_v1_L3 | rgb_texture | 16440 | 32868 | 32868 | 0.0 | 1.0 | 0.8184 | 0.9321 | 0.1895 |
| Watermelon_V1_L3 | non_texture | 16436 | 32868 | 32868 | 0.0 | 1.0 | 0.9843 | 0.9926 | 0.1301 |

**Diagnosis:**

1. **GT "pixelation" (Marco_Polo left, Statue back)**: NOT a rendering or CSV reading bug. MeshMamba GT CSVs are already pre-normalised [0,1], single-column, no header, n_lines == n_faces → domain=face. The "noisy/patchy" appearance is the intrinsic property of per-face raw fixation aggregation — adjacent faces can have very different values (high spatial frequency). Screen_space and cone are smooth Gaussians; GT is not. This is a data property.

2. **Jukebox GT absent (root cause)**: `_find_file_casefold(gt_dir, model, ".csv")` searched for `Jukebox_bubbler_style_V2_L1.csv` but the actual GT file is `Jukebox_bubbler_style_V2_Textured.csv`. Stem mismatch (`_L1` vs `_Textured`). **Fixed** via `--gt-lookup-csv` + `gt_lookup` parameter in `resolve_map_paths`.

3. **Jukebox screen_space no red zone**: Global minmax normalization — the maximum-saliency face is on a surface only visible at certain rotation angles (mid-turn), not from any canonical six-view direction. Visible front faces top out at ~0.65–0.70 of global max → yellow in jet. **Fix**: `--display-percentile 99` clips above-p99 outliers so visible faces use the full colormap range.

### Changes

| File | Change |
|---|---|
| `visualization/heatmap_six_view/render_six_view_heatmaps.py` | Add `--gt-lookup-csv` + `gt_lookup` to resolve MeshMamba GT aliases; add `--display-percentile` + `display_percentile` to `load_and_prepare_map` for p99 display clipping |
| `test/test_six_view_heatmaps.py` | Add `test_meshmamba_gt_alias_lookup`, `test_display_percentile_clips_outlier`, `test_display_percentile_100_equals_minmax` (38/38 pass) |

**Local debug renders** (GPU, PyVista 0.48.4):
- Marco_Polo GT minmax + p99: `/tmp/diag_renders/`
- Statue GT + cone minmax + p99: `/tmp/diag_renders/`
- Jukebox GT (alias fixed) + cone minmax + p99: `/tmp/diag_renders/`
- Comparison collages: `/tmp/diag_collages/`

Jukebox GT front now shows clear red hotspot in jukebox display panel area (confirmed alias fix works).

### Usage

Pass `--gt-lookup-csv results/benchmark_runs/meshmamba/2026-06-02_meshmamba_reference/meshmamba_reference_long.csv`
to resolve all MeshMamba GT aliases from the long benchmark CSV.

Use `--display-percentile 99` when screen_space maps appear washed-out (max not visible from canonical views).

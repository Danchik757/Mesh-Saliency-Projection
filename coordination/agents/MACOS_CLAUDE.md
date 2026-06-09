# macOS Claude: Processed Fixations, Timing, Evaluator Migration, and Release

## Identity

- Platform: macOS
- Branch: `agent/macos-ingestion-release`
- Base: immutable ref from `coordination/TASK_OWNERSHIP.md`
- Work log: append entries to the end of this file only
- Server execution: forbidden unless reviewer/controller explicitly requests it

## Mission

Remove the input-contract blockers that prevent correct metric runs. Make the new
postprocessed fixation JSON the explicit default benchmark input, implement the
approved one-turn timing pairing once, migrate all relevant evaluators/batches,
make report resume provenance-safe, and prepare a reproducible release candidate.

During Phase 1, do not change metric formulas, mesh-loading policy, alignment
transforms, sigma semantics, heatmaps, or research methods.

## Owned Paths

- `participant_data/` documentation and small indexes, not bulk payload in git
- new shared participant/timing loader under `utils/participant_*`
- `scripts/build_release_candidate.py`
- `scripts/validate_release_candidate.py`
- `scripts/validate_data_contract.py`
- `scripts/download_release_candidate.sh`
- `scripts/upload_release_candidate.sh`
- evaluator input/timeline adapters needed for processed JSON
- batch input/provenance/resume adapters
- tests dedicated to participant input, timing, provenance, and release contract

Do not edit:

- metric formulas or metric-owned tests;
- mesh-loading/preflight policy;
- alignment transforms/FOV behavior;
- visualization/video/sigma/research-method code;
- another role's coordination file;
- `trash/*.md` or `md/archive/*`.

## Required Initial Audit

Before edits:

1. Verify branch, HEAD, base ref, and dirty status.
2. Inspect every current evaluator and batch entry point for input type, frame
   mapping, out-of-range behavior, report provenance, and resume behavior.
3. Reproduce `coordination/RELEASE_AUDIT_2026-06-09.md`.
4. Reproduce the current failure in `scripts/validate_data_contract.py`.
5. Confirm the placement rotation arrays are sampled inclusively across declared
   duration. Do not treat the last sample timestamp as the full declared duration
   when validating rotation speed.
6. Append the audit and exact planned touched files before implementation.

## Milestone A1: Shared Processed-Fixation and Timing Loader

Implement one reusable loader. Do not duplicate parsing/timing logic per dataset.

Required behavior:

- identify dataset, track, and model unambiguously and case-insensitively without
  losing canonical output names;
- load `fixations.json` and the matching canonical placement JSON;
- validate structure, finite coordinates, bounds, frame counts, FPS, duration,
  and rotation information;
- expose frame-wise pixel points and paired placement frame metadata;
- derive the usable one-turn interval from placement JSON;
- pair exactly:
  `processed_gaze[k] -> placement[round(1.8 * fps) + k]`;
- consume exactly 450 processed frames for 17-second tracks and 660 for
  24-second SAL3D after derived validation;
- fail if crop duration is not one full turn within a documented tolerance;
- fail explicitly for invalid `3DVA_jessi` and missing `SAL3D_gorgoile`;
- never silently fall back to original CSV;
- provide an explicit old-CSV compatibility mode only;
- reject/drop old-CSV samples outside the selected interval, never clamp them to
  the last placement frame.

Required tests:

- valid 17-second pairing;
- valid 24-second pairing;
- invalid/missing processed file;
- coordinate/frame-count failure;
- rotation-speed/full-turn validation;
- old-CSV compatibility mode isolation;
- out-of-range sample rejection/drop.

## Milestone A2: Evaluator and Batch Migration

Migrate both accepted methods for every track:

- 3DVA screen-space and cone evaluators;
- MeshMamba non_texture and rgb_texture screen-space and cone evaluators;
- SAL3D screen-space and cone evaluators;
- their reference batch launchers.

Processed fixation JSON must be the default. Original CSV mode must require an
explicit compatibility flag and produce visibly different report provenance.

Every report must record at least:

- git commit;
- participant input type and source/version;
- dataset, track, model;
- placement JSON path/version;
- FPS and declared duration;
- crop start/end;
- processed frame count used;
- placement frame range;
- timing mode;
- method and parameters;
- support type;
- included/excluded reason where relevant.

Batch discovery must use the processed input inventory in the default mode.
Lowercase matching may be used internally, but output must retain canonical
model naming.

## Milestone A3: Resume and Single-Point Timing Proof

Resume may reuse a report only when its provenance fingerprint matches the
current task. At minimum the fingerprint must change with:

- git commit or evaluator version;
- release/data version;
- participant input type;
- timing/crop mode;
- placement JSON;
- model/track;
- method and parameters;
- support/GT mode.

Default to no resume until this behavior is tested.

Produce a deterministic single-point/frame debug proof for one representative
model from each track. The proof must record processed gaze index, paired
placement/video frame, coordinates, pose, and output preview. Compare at least
three frames per track against source video/placement timeline.

Do not alter alignment parameters to improve the preview. Report alignment
problems to the Windows worker.

## Milestone A4: Release Contract

Fix and complete the replacement release workflow:

- validator correctly handles inclusive placement rotation samples;
- canonical placement inventory is 299;
- old participant CSV and processed fixation JSON remain separate;
- release includes required OBJ/GT and dataset indexes;
- manifest records timing contract and known blockers;
- checksums and archive CRC pass;
- extraction into an empty directory passes;
- release-only input discovery passes.

Do not commit the approximately 517 MB participant payload into normal git.
Do not upload a release without reviewer/controller and user approval.

Target:

```text
v2.0-data-rc1
```

## Required Smoke Evidence

Before requesting integration:

- 3DVA: one valid model plus explicit `jessi` failure;
- MeshMamba non_texture: one valid model;
- MeshMamba rgb_texture: one valid model;
- SAL3D: one valid model plus explicit `gorgoile` failure;
- both methods reach evaluator/report generation for each valid track;
- every valid report proves the approved processed frame and placement range;
- resume mismatch test forces rerun;
- release validator and clean extraction pass.

These are smoke results, not final promoted metrics.

## Review Request Format

Append:

- milestone and commit hashes;
- exact files and commands;
- tests and outputs;
- known limitations;
- any required Windows-worker or reviewer decision;
- confirmation that branch is pushed and clean.

Then stop and wait for review. Do not self-integrate.

## Phase 2: Only After Full Runs Start

When explicitly authorized, this worker owns the isolated parameter/research
stream from the original plan:

1. document sigma semantics and units for both accepted methods;
2. implement a separate reproducible cross-dataset sigma sweep around previously
   promising values;
3. select representative model subsets without tuning on a single object;
4. produce tidy CSVs and plots for every relevant metric by dataset/track/method;
5. propose, justify from relevant research, and only after design approval
   implement one new projection method in an isolated directory.

Do not modify the accepted Phase 1 evaluators or promoted result directories.
Accepted metric experiments run on servers after reviewer/controller approval.

## Append-Only Work Log

Append new entries below. Never rewrite prior entries.

---

### Audit 2026-06-09 — Required Initial Audit (pre-implementation)

**Branch:** `reproject-benchmark`
**HEAD:** `684efc3 Fix 3DVA CombinedGT support logic and release packaging`
**BASE_REF `agent-base-2026-06-09`:** NOT YET PUBLISHED (no tags exist)
**Worker branch `agent/macos-ingestion-release`:** NOT YET CREATED
**Dirty status:** 35 modified files; 4 new untracked entries (`coordination/`,
`md/archive/WINDOWS_CHATGPT.md`, `participant_data/`,
`scripts/build_release_candidate.py` + remaining release scripts already
tracked). The entire `coordination/` package is uncommitted — consistent with
Decision 5 (reviewer/controller must publish BASE_REF before code edits).

---

#### Step 2: Evaluator and batch entry point inspection

All 8 production evaluators are **CSV-only**. No evaluator accepts processed
fixation JSON. No evaluator implements the approved 1.8 s/0.2 s timing crop.

| Script | Input | Frame mapping | Out-of-range | Provenance | Resume |
| --- | --- | --- | --- | --- | --- |
| `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py` | CSV | `min(floor(t*fps), total-1)` — CLAMPS | CLAMP (bug) | none | none |
| `reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py` | CSV | same | CLAMP (bug) | none | none |
| `reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py` | CSV | same | CLAMP (bug) | none | none |
| `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py` | CSV | same | CLAMP (bug) | none | none |
| `reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py` | CSV | same | CLAMP (bug) | none | none |
| `reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py` | CSV | same | CLAMP (bug) | none | none |
| `reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py` | CSV | same | CLAMP (bug) | none | none |
| `reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py` | CSV | same | CLAMP (bug) | none | none |

Batch launchers (Python): `run_3dva_reference_batch.py`,
`run_meshmamba_reference_batch.py`, `run_sal3d_reference_batch.py` — discover
models from filesystem CSV directories; no processed JSON discovery; no
provenance injection into sub-process invocations.

Batch launchers (shell): `run_3dva_screen_space.sh`, `run_3dva_raycast_cone.sh`,
`run_meshmamba_baseline_screen_space.sh`, `run_meshmamba_baseline_cone.sh`,
`run_sal3d_cone.sh` — pass `--csv-root` env var to evaluators; no processed
JSON flag.

**Additional script found:** `eval_meshmamba_screen_space_v2.py` — same CSV
input pattern; same clamp bug.

---

#### Step 3: RELEASE_AUDIT_2026-06-09 reproduction

`validate_release_candidate.py` requires a `candidate_dir` containing
`release_manifest.json`, `SHA256SUMS`, `data_contract_validation.json`, and the
archive ZIPs. No local release candidate directory exists, so the validator
cannot be run directly. All 8 blocking findings from the audit document were
confirmed by reading the validator source and `v1.0-data` asset list:

- Finding 1 (no processed fixation JSON): `participant_fixations_processed_offset_2000.zip`
  absent from `v1.0-data`; local `participant_data/processed_fixations_offset_2000/` is
  present locally but untracked/uncommitted.
- Finding 2 (wrong SAL3D placement JSONs in `camera_jsons.zip`): validator
  (`validate_release_candidate.py`) requires
  `object_placement_json_canonical.zip` with a canonical root; `v1.0-data`
  ships `camera_jsons.zip` instead.
- Finding 3 (`3dva_combined_gt.zip` absent): validator `REQUIRED_ARCHIVES` set
  includes `3dva_combined_gt.zip`; absent from `v1.0-data`.
- Findings 6–8 (no manifest, MeshMamba OBJ duplicate, GT coverage): validator
  expects `release_manifest.json` and `SHA256SUMS`; neither exists in `v1.0-data`.

---

#### Step 4: validate_data_contract.py failure reproduction

Command: `python3 scripts/validate_data_contract.py`

Exit code: **2** (known blockers present, no unknown errors)

Known blockers confirmed:
- `3DVA:invalid_processed:jessi` — processed JSON has 41 frames; placement JSON
  declares `total_frames=510`. Script correctly detects and classifies this.
- `SAL3D:missing_csv:gorgoile` — no CSV file in `collected_gaze_csv_by_model/SAL3D/`.
- `SAL3D:missing_processed:gorgoile` — no `SAL3D_gorgoile/fixations.json` in
  `processed_fixations_offset_2000/`.

All other 297 models pass placement, CSV, and processed JSON validation. Timing
groups are uniform across each track (single entry per track in `timing_groups`
dict).

---

#### Step 5: Placement rotation arrays — inclusive sampling check

Tested with `jsons/object_placement/3dva_jsons/3DVA_A380.json`:

```
total_frames = 510, fps = 30, declared duration_seconds = 17.0
frame[0]   rot_z = 0.000000 rad (0.00°)
frame[509] rot_z = 7.120944 rad (407.95°)
```

`validate_data_contract.py` line 210:
```python
observed_speed = (unwrapped[-1] - unwrapped[0]) / duration
```
Uses `duration` (17.0 s), NOT `timestamps[-1]` (= 509/30 = 16.967 s). The
comment on lines 207–209 explicitly documents this as the intentional fix.
Result: `observed_speed = 407.95° / 17.0 s ≈ 24.0 deg/s` — matches declared
`rotation_speed_deg_per_sec = 24.0`. Validation passes correctly.

`validate_release_candidate.py` performs no rotation speed check (archive
structure/checksum only). No fix required there.

**Conclusion:** rotation inclusive sampling is already correctly handled in
`validate_data_contract.py`. No change needed for step 5.

---

#### Step 6: Planned touched files (exact, before implementation)

New files (owned by this worker):
```
utils/participant_loader.py          — shared processed-fixation + timing loader
utils/__init__.py                    — package marker (if not already present)
test/test_participant_loader.py      — unit tests for loader (A1 required tests)
```

Modified files (evaluator input/timeline adapters):
```
reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py
reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py
reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py
reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py
reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py
reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py
reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py
reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py
```

Modified files (batch input/provenance/resume adapters):
```
test/launch/run_3dva_reference_batch.py
test/launch/run_meshmamba_reference_batch.py
test/launch/run_sal3d_reference_batch.py
test/launch/run_3dva_screen_space.sh
test/launch/run_3dva_raycast_cone.sh
test/launch/run_meshmamba_baseline_screen_space.sh
test/launch/run_meshmamba_baseline_cone.sh
test/launch/run_sal3d_cone.sh
```

No changes required (already correct):
```
scripts/validate_data_contract.py    — rotation inclusive sampling already fixed
scripts/validate_release_candidate.py — no rotation check here
```

Release tooling (owned by this worker, A4):
```
scripts/build_release_candidate.py   — already exists; needs manifest/inventory fixes
```

Do NOT touch:
```
reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space_v2.py
  — v2 is an experimental variant; canonical is eval_meshmamba_screen_space.py
  — will skip unless reviewer/controller instructs otherwise
eval_holdout_screenspace.py, eval_geodesic_diffusion.py, etc.
  — outside accepted two methods, not in scope
trash/*.md, md/archive/*, coordination/ (other agents' files)
```

---

**Audit status: COMPLETE**. Awaiting BASE_REF publication by reviewer/controller
before any implementation code edits. Will append milestone entries once worker
branch is created from BASE_REF.

---

### Milestone A1 — 2026-06-09

**Branch:** `agent/macos-ingestion-release`
**Commit:** `b46dd1e`
**BASE_REF:** `agent-base-2026-06-09` = `b232129`
**git status --short after push:** clean (no modified or untracked files)

#### Files changed

New files:
```
utils/participant_loader.py        — shared processed-fixation and timing loader
test/test_participant_loader.py    — 14 unit tests for all A1 required behaviors
```

No existing files modified in this milestone.

#### Commands run

```
# Development
python3 -m pytest test/test_participant_loader.py -v
# All 14 tests pass; output: "14 passed in 0.39s"

# Smoke test on real participant data (read-only, data from main repo path):
# python3 smoke_script.py  (inline script, not committed)
# Results below under "Actual results".

# Commit and push
git add utils/participant_loader.py test/test_participant_loader.py
git commit -m "A1: Add shared processed-fixation and timing loader"
git push origin agent/macos-ingestion-release
```

#### Input data version and model/track

Real data smoke test used local participant_data from the main repo
(`Mesh-Saliency-Projection`), not committed to git (517 MB payload).
- 3DVA track: model `A380`, placement `3DVA_A380.json`
- SAL3D track: model `horse`, placement `Sal3D_horse.json`
- Blocker models: `jessi` (3DVA), `gorgoile` (SAL3D)

#### Expected vs actual results

| Test | Expected | Actual |
| --- | --- | --- |
| 3DVA A380 (processed JSON) | usable=450, start=54, end=504, 450 batches | ✓ all match |
| SAL3D horse (processed JSON) | usable=660, start=54, end=714 | ✓ all match |
| 3DVA jessi | `InvalidFixationError` (41 != 510) | ✓ raised, "fall back" in message |
| SAL3D gorgoile | `MissingFixationError` | ✓ raised, "fall back" in message |
| 3DVA A380 CSV compat | 450 in-window frames, drops out-of-window | ✓ 45684 dropped, 0 frames outside window |
| Unit tests 14/14 | all pass | ✓ |

**Significant finding:** CSV compat loader dropped 45,684 out-of-window gaze samples for A380 alone — samples the old evaluator was silently clamping to the last placement frame. This confirms the critical impact of the approved timing contract.

#### Output paths

No output directories (loader is a library module, not a script).

#### Known limitations / open questions

1. **No `__init__.py` in `utils/`**: The existing module `utils/path_defaults.py` is already imported without one (evaluators add REPO_ROOT to sys.path). Consistent with the existing convention.
2. **Out-of-bounds pixel points in processed JSON**: The loader silently drops them (no error). The `validate_data_contract.py` already confirmed there are none in the valid dataset files. If a future file contains them they will be dropped and a comment in the code explains this.
3. **CSV compat resolves CSV file naming itself**: The real CSVs are named `A380.csv` not `3DVA_A380.csv`. Callers must pass the correct path. This is intentional — the caller (evaluator or batch launcher) knows the naming convention for its dataset.
4. **`GazeBatch` type replaces per-evaluator `FrameGazeBatch`**: Evaluators in A2 should import `GazeBatch` from `utils.participant_loader` and remove their local `FrameGazeBatch` definition. Both have identical fields (`x_norm`, `y_norm`).

#### Confirmed clean push

```
git status --short  →  (empty, clean)
git log --oneline -1  →  b46dd1e A1: Add shared processed-fixation and timing loader
```

---

### A2 Pre-plan (no code changes — awaiting A1 review)

Planning note only. No implementation until reviewer approves A1 and lifts
the review gate.

#### Evaluators to migrate (8 scripts)

Each script needs the same three changes:
1. Replace `--csv-root` default path with `--fixation-root` pointing to
   `participant_data/processed_fixations_offset_2000/`; keep `--csv-root`
   behind an explicit `--csv-compat` flag.
2. Replace the local `FrameGazeBatch` dataclass definition + `load_gaze_batches()`
   CSV function with a single call to `load_processed_track()` (or
   `load_csv_compat_track()` when `--csv-compat` is set). Remove the
   `min(..., total_frames - 1)` clamp.
3. Inject `track.provenance` into the output report JSON under a
   `"participant_input"` key alongside the existing metrics.

Scripts:
```
reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py
reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py
reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py
reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py
reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py
reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py
reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py
reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py
```

#### Batch launchers to migrate (8 files)

Python launchers: replace CSV-directory discovery with processed-JSON
directory discovery; pass `--fixation-root` (or `--csv-compat --csv-root`)
to evaluators; inject `input_mode` into per-model batch rows.

Shell launchers: add `FIXATION_ROOT` env var; forward `--fixation-root` to
evaluator; document `--csv-compat` flag.

```
test/launch/run_3dva_reference_batch.py
test/launch/run_meshmamba_reference_batch.py
test/launch/run_sal3d_reference_batch.py
test/launch/run_3dva_screen_space.sh
test/launch/run_3dva_raycast_cone.sh
test/launch/run_meshmamba_baseline_screen_space.sh
test/launch/run_meshmamba_baseline_cone.sh
test/launch/run_sal3d_cone.sh
```

#### Key decisions needed from reviewer before A2 code

1. **`canonical_name` resolution for MeshMamba**: processed JSON dirs are named
   `MeshMamba_non_texture_<model>` and `MeshMamba_rgb_texture_<model>`. The
   `canonical_name` passed to `load_processed_track` should be the full dir
   name (e.g. `MeshMamba_non_texture_Ice_Cream_V1_L3`), with `dataset` =
   `MeshMamba_non_texture` and `model` = `Ice_Cream_V1_L3`. Confirm this
   is the intended naming for report output.

2. **`--csv-compat` flag name**: confirm this is the approved name (vs
   `--use-csv`, `--legacy-csv`, etc.) so all 8 evaluators + batch launchers
   use the same flag.

3. **Placement JSON lookup in evaluators**: currently evaluators accept
   `--json-root` (3DVA) or similar. After migration `load_processed_track`
   takes `placement_path` directly. Confirm that the existing `--json-root`
   / `THREE_DVA_JSON_ROOT` env var convention is retained and the loader is
   called with the resolved path (not a root dir).

4. **Report key name for provenance**: confirm `"participant_input"` is the
   agreed key name for the provenance dict in the output JSON report, or
   specify another name.

These are blocking for correct A2 implementation; will not start code until
confirmed by reviewer.

---

### A1 fix — 2026-06-09

**Branch:** `agent/macos-ingestion-release`
**Commit:** `133c08f`
**git status --short after push:** clean

**Required fix from reviewer:** out-of-bounds pixel points in processed JSON
must raise `InvalidFixationError`, not be silently dropped.

**Rationale (reviewer's):** `validate_data_contract.py` already confirms no
valid release file contains out-of-bounds points. An out-of-bounds point
reaching the loader is a data-contract violation, not a normal condition.

**Files changed:**
```
utils/participant_loader.py   — replace silent drop with InvalidFixationError;
                                added comment explaining the rationale
test/test_participant_loader.py — test_out_of_bounds_points_dropped renamed to
                                  test_out_of_bounds_points_raises; now asserts
                                  InvalidFixationError with "out-of-bounds" in message
```

**Result:** 14/14 tests pass. Branch pushed and clean.

**A2 decisions confirmed by reviewer:**
1. MeshMamba canonical_name = full processed dir stem (e.g.
   `MeshMamba_non_texture_Ice_Cream_V1_L3`); report additionally stores
   `dataset` and `model` split.
2. CSV compat flag: `--csv-compat`.
3. Evaluators retain `--json-root` / env convention; resolve placement_path
   themselves before passing to loader.
4. Report provenance key: `participant_input`.

Waiting for reviewer to lift A2 gate.

---

### Milestone A2 — 2026-06-09

**Branch:** `agent/macos-ingestion-release`
**BASE_REF:** `agent-base-2026-06-09` = `b232129`
**A1 commits:** `b46dd1e`, `133c08f` (fix: out-of-bounds raises InvalidFixationError)

#### Files changed (16 total)

Evaluators (8 scripts) — all now default to processed JSON via `--fixation-root`;
legacy CSV behind explicit `--csv-compat`; no clamping path in processed/default
mode; all reports include `"participant_input": track.provenance`:
```
reprojection_methods/screen_space_gaussian/eval_3dva_screen_space.py
reprojection_methods/screen_space_gaussian/eval_3dva_screen_space_combined.py
reprojection_methods/cone_projection_on_mesh/eval_3dva_raycast_cone.py
reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py
reprojection_methods/screen_space_gaussian/eval_meshmamba_screen_space.py
reprojection_methods/cone_projection_on_mesh/eval_meshmamba_cone.py
reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py
reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py
```

Python batch launchers (3 scripts) — discover models from processed JSON
(`<DATASET>_*/fixations.json`) by default; pass `--fixation-root` or
`--csv-compat --csv-root` to evaluators; resume skips only when
`participant_input` provenance matches current mode/timing contract:
```
test/launch/run_3dva_reference_batch.py
test/launch/run_meshmamba_reference_batch.py
test/launch/run_sal3d_reference_batch.py
```

Shell launchers (5 scripts) — accept `FIXATION_ROOT` / `CSV_COMPAT` env vars;
default to `--fixation-root $FIXATION_ROOT`; `CSV_COMPAT=true` falls back to
CSV with explicit `--csv-compat --csv-root`:
```
test/launch/run_3dva_screen_space.sh
test/launch/run_3dva_raycast_cone.sh
test/launch/run_meshmamba_baseline_screen_space.sh
test/launch/run_meshmamba_baseline_cone.sh
test/launch/run_sal3d_cone.sh
```

#### Key per-evaluator changes (shared pattern)

- Removed local `@dataclass class FrameGazeBatch`; replaced with
  `FrameGazeBatch = GazeBatch` alias imported from `utils.participant_loader`.
- Removed `load_gaze_batches()` CSV function and all CSV imports (`ast`,
  `defaultdict`, `dataclass`, `pandas`, `csv`).
- Added `--fixation-root` and `--csv-compat` CLI args.
- Added `_load_gaze_track(args, placement_path)` helper: routes to
  `load_processed_track()` or `load_csv_compat_track()` based on flag.
- Removed `"csv"` from `ensure_required_exist()` / `resolve_model_paths()`
  return dicts in default mode.
- Added `"participant_input": track.provenance` to every report dict.

#### MeshMamba canonical_name

`f"MeshMamba_{texture_type}_{model}"` — e.g. `MeshMamba_non_texture_Ice_Cream_V1_L3`.
Consistent with approved A2 decision.

#### Resume provenance contract (`_provenance_matches`)

All three Python launchers check before reusing any existing report:
- `input_mode` == `"processed_json"` (or `"csv_compat"` when `--csv-compat`)
- `crop_start_seconds` ≈ 1.8 (±1e-6)
- `crop_end_seconds` ≈ 0.2 (±1e-6)

Reports with a different participant/timing contract trigger a rerun.

#### Syntax checks

```
# All 8 evaluators
python3 -c "import ast; ast.parse(...)"  →  all OK

# All 5 shell launchers
bash -n <script>  →  all OK
```

#### Known limitations

1. **Smoke evidence not yet collected** — server execution is forbidden on
   macOS worker. The A2 acceptance smoke tests (valid 3DVA model, MeshMamba
   non+rgb, SAL3D, expected `jessi`/`gorgoile` failures) require server runs
   that the reviewer/controller must authorize and execute.
2. **MeshMamba rgb_texture batch launcher** — no dedicated `run_meshmamba_rgb_reference_batch.py`
   was found in the repository; the existing `run_meshmamba_reference_batch.py`
   handles both texture types via `--texture-type` arg. Migrated accordingly.
3. **`eval_meshmamba_screen_space_v2.py`** — out-of-scope experimental variant;
   not migrated per audit decision.

#### Awaiting review

Branch pushed. Requesting reviewer to:
1. Verify all 16 changed files against A2 acceptance criteria.
2. Run smoke tests on server (`jessi` expected failure, `gorgoile` expected
   failure, one valid model each track/method).
3. Confirm before A3 or any server jobs begin.

---

### A2 fix — env alias support — 2026-06-09

**Branch:** `agent/macos-ingestion-release`
**Blocking issue:** A2 code accepted only `FIXATION_ROOT`; server env files define
`REPROJECT_PROCESSED_FIXATIONS_ROOT` and dataset-specific roots. Batch failed
with `--fixation-root not found: None` after sourcing `configs/server_vg_intellect.env`.

**Files changed (16):**

All 8 evaluators — `--fixation-root` argparse default now checks env aliases in
priority order via `next((...), None)`:
- 3DVA (4 files): `FIXATION_ROOT` → `REPROJECT_PROCESSED_FIXATIONS_ROOT` → `THREE_DVA_PROCESSED_FIXATIONS_ROOT`
- MeshMamba (2 files): `FIXATION_ROOT` → `REPROJECT_PROCESSED_FIXATIONS_ROOT` → `MESHMAMBA_PROCESSED_FIXATIONS_ROOT`
- SAL3D (2 files): `FIXATION_ROOT` → `REPROJECT_PROCESSED_FIXATIONS_ROOT` → `SAL3D_PROCESSED_FIXATIONS_ROOT`

Python batch launchers (3 files):
- `run_3dva_reference_batch.py`: `_env_path()` call extended with 3DVA aliases
- `run_meshmamba_reference_batch.py`: `resolve_fixation_root()` checks 3 keys; error message updated
- `run_sal3d_reference_batch.py`: same pattern with SAL3D key

Shell launchers (5 files): `FIXATION_ROOT` fallback chain extended:
- 3DVA scripts: `…${REPROJECT_PROCESSED_FIXATIONS_ROOT:-${THREE_DVA_PROCESSED_FIXATIONS_ROOT:-${REPROJECT_FIXATION_ROOT:-}}}}`
- MeshMamba scripts: `…${REPROJECT_PROCESSED_FIXATIONS_ROOT:-${MESHMAMBA_PROCESSED_FIXATIONS_ROOT:-${REPROJECT_FIXATION_ROOT:-}}}}`
- SAL3D script: `…${REPROJECT_PROCESSED_FIXATIONS_ROOT:-${SAL3D_PROCESSED_FIXATIONS_ROOT:-${REPROJECT_FIXATION_ROOT:-}}}}`

**Verified:** inline test confirms `REPROJECT_PROCESSED_FIXATIONS_ROOT` and
dataset-specific env vars each resolve correctly; missing-all → `None` still
triggers the existing validation error.

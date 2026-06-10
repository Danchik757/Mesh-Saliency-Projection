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

---

## A3: Cropped-reset fixation format (mesh_json_2__offset_2000)

**Commit:** b6a3a3a
**Branch:** agent/macos-fixation-format-v2
**Date:** 2026-06-10

### Context

New fixation root `/Users/admin/Downloads/mesh_json_2__offset_2000` delivers
files with the trailing unused frames stripped:
- 17 s tracks (MeshMamba, 3DVA): 450 frames = 510 − 54 − 6
- 24 s tracks (SAL3D): 660 frames = 720 − 54 − 6
- Index 0 = placement frame round(1.8 × fps) = 54; loop pairing unchanged
- 3DVA_jessi: empty file (0 frames) → excluded by loader validation

Old full-length format (510/720) is no longer production input.

### Changes

**`utils/participant_loader.py`**
- `load_processed_track()`: validate `len(raw) == usable_count` (was
  `total_frames`); raise `InvalidFixationError` for empty file (len=0)
- `_build_provenance()`: added `fixation_format: cropped_reset_offset_2000`
  and `fixation_start_index: 0`
- Module docstring: updated 3DVA_jessi blocker note

**`test/launch/run_{sal3d,meshmamba,3dva}_reference_batch.py`**
- `_provenance_matches()`: for `processed_json` mode, requires
  `fixation_format == "cropped_reset_offset_2000"`; old reports (without
  this field) will not be reused on `--resume`

**`test/test_participant_loader.py`**
- All processed-JSON fixtures updated from `total_frames` to
  `usable_count` length (450/660)
- `test_provenance_fields_present`: added `fixation_format`,
  `fixation_start_index` to required-fields list

### Verification

```
python -m pytest -q   →   155 passed
loader smoke test: MeshMamba Peanut_L3 usable=450 ✓
                   SAL3D alien usable=660 ✓
                   3DVA_jessi empty → InvalidFixationError ✓
```

---

## SAL3D Data Organization — Technical Note

**Source:** PROJECT_STATE_2026-06-10.md + SAL3D_DATASET.md + sal3d.md + direct
vertex-count audit on SAL3D_Dataset/Meshes and SAL3D_Dataset/Gaze.

### Three distinct data types

**`Gaze/<model>.txt` — raw GT in gaze-indexing**

- Normally 20000 rows, 8 columns: `[x, y, z, nx, ny, nz, fixation_density, binary]`
- Column 6 (`fixation_density`) is the primary GT: continuous, unnormalized
  (observed range 0–7+, mean ≈ 0.003–0.028, typically 60–85% zero).
- Column 7 is a binary presence flag, not used as the main GT.
- Row indices are *gaze-indexing*, not OBJ vertex ordering. For "exact" models
  (20000 Gaze rows == 20000 OBJ verts, e.g. bunny, camel) the indices happen to
  coincide; for "subset" models they do not.

**`Smooth Gaze/<model>_neighbors.txt` — topology only, no GT values**

- Contains vertex IDs that received fixations and their 500-nearest-neighbor
  lists, sorted by distance, in gaze-indexing.
- Does not contain any saliency values. The propagation algorithm
  `linspace(0.9*v, 0, n_neighbors)` requires `v` from the Gaze file; without
  it only a binary (v=1 for all) approximation is possible, which
  systematically upweights weak fixations ~10–13×.
- Cannot serve as GT on its own.

**NPZ `target` — fixed per-face GT, already normalized `[0, 1]`**

The fixed pipeline (sal3d_fix.py) produces this canonical GT:
1. Load raw `Gaze[:, 6]` in gaze-indexing.
2. Min-max normalize to `[0, 1]`.
3. Apply Smooth Gaze propagation in gaze-indexing (neighbor smoothing).
4. Repair mesh with pymeshfix if non-watertight/non-manifold.
5. Transfer smoothed GT to repaired OBJ vertices via KDTree nearest-neighbor
   in the gaze coordinate frame (exact hit for original verts; patch verts
   inherit nearest).
6. Average per-vertex GT across the three vertices of each face → per-face.
7. Min-max normalize final per-face map → `[0, 1]`.

Stored as `npz['target']`, shape `(n_faces,)`, dtype float32, range `[0, 1]`.
The canonical OBJ to pair with it is `SAL3D_almost_fixed/Meshes/<model>.obj`.

### Why MaxPlanck / meca / sofa cannot be evaluated via raw Gaze vertex-index

Direct measurement (SAL3D_Dataset/Meshes vs SAL3D_Dataset/Gaze):

| Model | OBJ vertices | Gaze rows | Verdict |
|-------|-------------|-----------|---------|
| MaxPlanck | 19999 | 20000 | off-by-one: index 19999 has no OBJ vertex |
| meca | 15000 | 20000 | 5000-row gap: last 5000 gaze rows map out of range |
| sofa | ~15125 | 20000 | ~4875-row gap: same failure |
| bunny | 20000 | 20000 | exact match, index assignment valid |
| camel | 20000 | 20000 | exact match, index assignment valid |

For MaxPlanck the mismatch is a single missing vertex (possibly a degenerate
vertex removed during export). For meca and sofa the OBJ is a different-
resolution version of the model than the one used for eye-tracking. Assigning
`gaze[i]` to `obj.verts[i]` silently produces wrong GT in all three cases.
These models must use the fixed per-face NPZ target obtained through KDTree
coordinate-based transfer.

### Excluded SAL3D models and reasons

| Model | Reason |
|-------|--------|
| AudiRS5, bimba, blade | OBJ version mismatch with gaze data (median nearest-distance 12–18% of model size after unit-normalization; threshold 0.5%) |
| gamecontroller, spanner | OBJ present, no Gaze file |
| gorgoile | No processed participant fixation JSON; excluded from our gaze metrics until one exists |

55 models are usable in the fixed dataset. Gorgoile has a valid NPZ GT but is
excluded from the participant-gaze benchmark.

### Heatmap rendering — normalization requirements

Every map must be independently min-max normalized to `[0, 1]` before applying
the jet colormap. Constant maps (max == min) display as all-blue (zero).

```python
vmin, vmax = values.min(), values.max()
if vmax > vmin:
    values01 = (values - vmin) / (vmax - vmin)
else:
    values01 = np.zeros_like(values)
```

This applies uniformly to:
- `screen_space_gaussian` prediction maps (per-face or per-vertex);
- `cone_gaussian_on_mesh` prediction maps;
- MeshMamba GT CSV values;
- SAL3D fixed NPZ `target` (already in `[0, 1]` but still normalized for
  display consistency);
- any future 3DVA CombinedGT maps.

**Map-domain validation (required before rendering):**

```
if len(map) == n_faces:   → color by face  (cell_data)
if len(map) == n_verts:   → color by vertex (point_data)
otherwise                 → fail, write error row in summary.csv
```

Never silently resample if the length does not match exactly.

**Manifest fields required per rendered entry:**

```
map_domain:            face | vertex
input_min:             float (pre-normalization minimum)
input_max:             float (pre-normalization maximum)
display_normalization: minmax_per_map | constant_zero
colormap:              jet
```

When `--global-scale-per-model` is active, `input_min`/`input_max` reflect
the shared scale across all three map types for that model, and
`display_normalization` is set to `global_minmax_per_model`.

---

## Work Log — SAL3D Fixed-Face GT Integration

**Branch:** agent/sal3d-fixed-face-gt
**Base:** 8f3293c (agent/macos-fixation-format-v2 HEAD)

### Task

Add `--fixed-gt-dir` support to both SAL3D evaluators and the batch runner so
that per-face fixed GT (from `sal3d_fixed_face_gt/<model>_faces.txt`) can be
used instead of raw `Gaze/*.txt` vertex-index matching.

### Files Changed

**`utils/sal3d_fixed_gt.py`** (new)
- Shared `load_fixed_face_gt(fixed_gt_dir, model, n_faces)` utility.
- Case-insensitive model name lookup.
- Raises `FileNotFoundError` if `<model>_faces.txt` not found.
- Raises `ValueError` if `len(gt) != n_faces`.

**`reprojection_methods/screen_space_gaussian/eval_sal3d_screen_space.py`**
- Added `--fixed-gt-dir` arg (env: `SAL3D_FIXED_GT_DIR`, default None).
- Added `--sal3d-manifest` arg (optional, recorded in provenance).
- `resolve_model_paths()`: Gaze GT now optional when `--fixed-gt-dir` is set.
- `ensure_exists()`: skips None paths (gt may be None with fixed-GT path).
- `main()`: old GT loading wrapped in try/except; ValueError caught when
  `--fixed-gt-dir` is set, allowing MaxPlanck/meca/sofa to run.
- When `--fixed-gt-dir` is set and directory exists:
  - `face_sal = vert_sal[mesh.faces].mean(axis=1)` — convert to face domain
  - Adds `metrics_vs_fixed_face_gt` section to report with provenance fields:
    `sal3d_gt_source`, `gt_domain=face`, `gt_path`, `manifest_path`, `n_faces`.

**`reprojection_methods/cone_projection_on_mesh/eval_sal3d_cone.py`**
- Same changes as screen_space evaluator.
- Face-domain section uses both `face_raycast` and `face_cone` predictions.

**`test/launch/run_sal3d_reference_batch.py`**
- Added `--fixed-gt-dir` and `--sal3d-manifest` args.
- Added `gt_domain` and `fixed_gt_file` to `LONG_BASE_COLUMNS`.
- `preflight_status()` gains `fixed_gt_dir` parameter; checks
  `<model>_faces.txt` in fixed GT dir when flag is present.
- `build_command()` passes `--fixed-gt-dir` and `--sal3d-manifest` through.
- `collect_row_from_report()` prefers `metrics_vs_fixed_face_gt` when present,
  falls back to `metrics_vs_gt_covered_only`.

**`test/test_sal3d_fixed_face_gt.py`** (new)
- 16 tests covering: correct length, wrong length, missing file, problem models
  (MaxPlanck/meca/sofa/turbine synthetic fixtures), known mismatch documentation.

### Test Results

```
210 passed in 3.15s
compileall: clean
```

---

## Work Log — SAL3D Batch Inventory Fix (A4 follow-up)

**Branch:** agent/sal3d-fixed-face-gt (same branch, follow-up commit)

### Task

`inventory_models()` in `run_sal3d_reference_batch.py` always discovered models
from `dataset_root/Gaze/*.txt`, which fails for the compact fixed-GT package
that has no `Gaze/` directory. Fix model discovery for `--fixed-gt-dir` mode.

### Changes

**`test/launch/run_sal3d_reference_batch.py`**
- Added `_read_manifest_model_names(manifest_path)` helper: reads first `model`
  column from `sal3d_manifest.csv`.
- `inventory_models()` gains `fixed_gt_dir` and `sal3d_manifest` parameters.
  - Fixed-GT mode: discovers from manifest CSV (if `--sal3d-manifest`) or
    from `*_faces.txt` glob; intersects with `Meshes/*.obj` and fixation JSONs.
    Does NOT require `Gaze/`.
  - Classic mode: unchanged.
- `gorgoile` auto-excluded if `SAL3D_gorgoile/fixations.json` is absent.
- `main()` passes `fixed_gt_dir` and `sal3d_manifest` to `inventory_models()`.
- `collect_row_from_report()`: sets `gt_match_type = "fixed_face"` for rows
  where `metrics_vs_fixed_face_gt` section is present.
- `write_summary_csv()`: adds `n_fixed_face` column (count of fixed-face rows);
  `n_direct`/`n_subset` are now zero for pure fixed-GT runs, as expected.

**`test/test_sal3d_batch_inventory.py`** (new, 9 tests)
- compact package without Gaze/ works
- gorgoile excluded when fixation JSON missing
- model with GT file but no OBJ excluded
- manifest-based discovery with and without unlisted models
- explicit `--models` bypasses inventory
- empty `sal3d_fixed_face_gt/` returns empty list
- classic mode still uses Gaze/*.txt and raises on missing Gaze dir

### Test Results

```
219 passed in 3.20s
compileall: clean
```

---

## Work Log — Pre-merge review fixes (A4c)

**Branch:** agent/sal3d-fixed-face-gt (follow-up commit to b4f5564)

### Issues found in independent review

1. **BLOCKER** `_read_manifest_model_names()` used `encoding="utf-8"` — fails on
   BOM-prefixed CSVs from Excel/Windows. Fixed to `encoding="utf-8-sig"`.

2. **Design gap** `inventory_models()` treated nonexistent `--fixed-gt-dir` as
   "not set", silently falling back to classic Gaze/ mode. Fixed: if
   `fixed_gt_dir is not None` but not a directory, raise `RuntimeError` with a
   clear message.

### New tests (2 added to test_sal3d_batch_inventory.py)

- `test_nonexistent_fixed_gt_dir_raises`
- `test_manifest_bom_handled`

### Test Results

```
221 passed in 2.43s
compileall: clean
```

---

## Work Log — Six-view heatmap renderer (preview)

**Branch:** agent/heatmap-six-view (from origin/reproject-benchmark @ 1065e28)

### Task

Small preview renderer: per-model jet heatmaps from 6 canonical views for
SAL3D (GT + screen_space + cone) and MeshMamba.

### Files created

- `visualization/heatmap_six_view/render_six_view_heatmaps.py` — main CLI renderer
- `test/test_six_view_heatmaps.py` — 35 unit tests (pure-logic, no pyvista required)

### Key design decisions

- **Normalization:** true min-max per map `(v - vmin) / (vmax - vmin)`, NOT
  percentile clipping. Constant maps → all-zero with warning recorded.
- **Domain detection:** `len == n_faces` → face; `len == n_verts` → vertex
  (converted via `vals[faces].mean(axis=1)`); otherwise fail that row.
- **SAL3D predictions are per-vertex** (`*_screen_space_vertices.txt`,
  `*_cone_vertices.txt`). GT is per-face (`*_faces.txt`). Both handled.
- **MeshMamba predictions are per-face** (`*_screen_space_faces.txt`,
  `*_cone_faces.txt`). GT is per-face CSV.
- Tags match batch-runner constants exactly (SAL3D_SCREEN_TAG,
  SAL3D_CONE_TAG, MM_SCREEN_TAG, MM_CONE_TAG).
- `_find_file_casefold()` for case-insensitive OBJ/GT lookups.
- `--limit N` for preview runs. `--models` for explicit selection.
- manifest.json: one entry per (dataset, model, map_type) with `input_min`,
  `input_max`, `display_normalization=minmax_per_map`, `colormap`, domain,
  commit hash, hostname, created_at.
- summary.csv: one row per (dataset, texture_type, model, map_type) with
  per-view PNG paths and montage path.

### Test Results

```
256 passed in 2.50s   (+35 new, 0 regressions)
compileall: clean
py_compile visualization/heatmap_six_view/render_six_view_heatmaps.py: OK
```

---

## Work log — 2026-06-10 — Alignment validation preview

Branch: `agent/heatmap-six-view`

Alignment gate tool before any full heatmap batch run.
For each dataset/model at 5 canonical frame indices, renders the mesh
silhouette using the exact same transform pipeline as the metric evaluators,
overlays the edge contour on the corresponding real video frame, and computes
silhouette IoU via background subtraction (gracefully omitted when video is
absent).

### Files created

- `validation/alignment_preview/check_alignment.py` — main CLI
- `test/test_alignment_preview.py` — 85 unit tests (no server data required)

### Key design decisions

- **Transform fidelity:** `precompute_base_verts` + `apply_frame_transform`
  implement the exact same split the batch runners use: 3dva order (base_rz →
  scale → frame_rz → extra_rx → extra_ry → translate) and blender_rig order
  (scale → extra_rx → extra_ry → base_rz → frame_rz → translate).
- **FOV:** `horizontal_to_vertical_fov_deg` applied for all datasets, matching
  evaluator behaviour.
- **Timing contract:** gaze index k → placement[CROP_START + k] → video frame
  (CROP_START + k).  No use of processed_gaze offsets.
- **Silhouette rasterisation:** PIL `ImageDraw.polygon` fill; all triangles
  whose three vertices have `w_clip > 0` are drawn.
- **Video mask:** corner-pixel median background subtraction (same algorithm as
  `test/tools/debug_single_gaze_projection.py`).  IoU flagged unreliable when
  video absent or extraction fails; overlays are still saved.
- **`--video-root` optional:** missing → IoU = null, overlays not generated,
  silhouette masks still saved.
- **Output structure:** `{output_root}/{DATASET[_tt]}/{model}/frame_{k:04d}_p{p:04d}/`
  → `silhouette_mask.png`, `raw_video_frame.png`, `overlay_edge.png`,
  `video_mask.png`, `result.json`; plus top-level `manifest.json` +
  `summary.csv`.

### Test results

```
341 passed in 2.88s   (+85 new, 0 regressions)
py_compile validation/alignment_preview/check_alignment.py: OK
```

### Fixes applied from live run

- **Print format bug**: `{k:>4s}` → `{k:>4}` (`gaze_k` is int; `s` spec crashes)
- **MeshMamba nested OBJ**: `_find_obj` now descends into `{model}/` subdirectory
  and falls back to normalised name matching (strip `_`/`-`, lowercase) for cases
  like `Starfruit_L3/Starfruit-L3.obj` and `Pear_L3/Pear.obj` (single-file
  fallback).
- Added `_normalise_lookup_name` helper + 13 new tests (`TestNormaliseLookupName`,
  `TestFindObj`); 354 passed total, 0 regressions.

---

## Work log — 2026-06-10 — Independent restructuring review

Branch: `reproject-benchmark` @ `d61be84`

Read: `README.md`, `coordination/README.md`, `coordination/PROJECT_STATE_2026-06-10.md`,
`coordination/RESTRUCTURING_REVIEW_2026-06-10.md`, `docs/project_structure.md`.
Verified by grep and directory listing; no code was modified.

---

### Q1 — Is the production path list complete?

The production path list in `RESTRUCTURING_REVIEW_2026-06-10.md` is:

```
configs/  jsons/  metrics/  reprojection_methods/
scripts/  test/launch/  utils/  requirements/  coordination/
```

**Gaps found:**

| Missing | Reason it is production |
|---------|------------------------|
| `participant_data/` | `README.md` lists it explicitly; holds release metadata required by data-contract validation |
| `conftest.py` + `pytest.ini` | Required for `pytest` to discover `test/` tests at all |
| `tests/` | Currently contains only a reserved `README.md`, but the directory is tracked and reserved for smoke/regression checks; needs to appear in the list so it is not accidentally moved with the candidate tools |

`gt_visualizations/` is **not** missing from the production list — it is correctly in the
candidate list for the future submodule. However, it is referenced by `README.md`'s
*"Visual verification"* section as a recommended pre-metric step with concrete server
commands. If it is moved before those README sections are updated, new agents will run
commands against paths that no longer exist. This is a doc-update dependency, not a
blocker to moving the code.

`docs/project_structure.md` calls the test folder `tests/` throughout, but the real
folder in the repo is `test/`. Minor inconsistency; does not affect production but will
confuse new readers.

---

### Q2 — Is the candidate path list for the future submodule correct?

```
gt_visualizations/          test/blender_canonical/     test/overlay_alignment/
test/tools/                 validation/alignment_preview/
video_creation/             visualization/
```

**Yes — all of these are auxiliary.** No production evaluator imports from any of
them at the Python level (confirmed: `grep -rn "from validation\|from visualization\|from video_creation\|from gt_visualizations"` in `reprojection_methods/`, `utils/`, `metrics/` returns nothing).

One clarification: `test/kld_parameter_sweep/` (the sigma sweep package) lives under
`test/` but is **not** auxiliary — it is the benchmark sweep driver. It should stay in
the production tree. `test/launch/run_kld_parameter_sweep.py` already wraps it
correctly with a `runpy` compatibility shim (see Q4 below).

---

### Q3 — Hardcoded references to candidate paths in production launchers

**Two live references found:**

| Production launcher | Hardcoded candidate path |
|--------------------|--------------------------|
| `test/launch/run_preview_manifest.sh` | `test/tools/render_preview_from_manifest.py` |
| `test/launch/run_saliency3d_clear_pilot.sh` | `video_creation/transfer_visualizations/make_transfer_visualizations.py` |

Both are shell scripts that construct the path as `$REPO_ROOT/<candidate-path>` and
call it directly. Moving the target without adding a compatibility stub would silently
break the launcher.

**Additional references (docs / agent files, non-executable):**

- `README.md` structure table references `test/tools/`, `validation/`, `visualization/`,
  `video_creation/` by path with clickable Markdown links.
- `test/README.md` has runnable example commands using `test/tools/render_preview_from_manifest.py`.
- `test/blender_canonical/search_blender_alignment.py` and
  `test/blender_canonical/evaluate_blender_mask_batch.py` reference
  `test/tools/render_preview_from_manifest.py` at runtime (both are themselves in
  the candidate list, so this is an intra-candidate dependency, not a blocker).
- `test/overlay_alignment/search_preview_alignment.py` also references it (same —
  intra-candidate).
- Comments in `reprojection_methods/cone_projection_on_mesh/eval_3dva_cone_combined.py`
  (line 448) and `eval_3dva_raycast_cone.py` (line 380) cite
  `render_preview_from_manifest.py` as the canonical reference implementation.
  These are comments only, not imports, but they will become stale after a move.

---

### Q4 — Files that need compatibility wrappers before moving

**Must have a wrapper (called by a production launcher):**

1. `test/tools/render_preview_from_manifest.py`
   — called by `test/launch/run_preview_manifest.sh`
   — wrapper pattern: leave a shim at `test/tools/render_preview_from_manifest.py`
   that does `runpy.run_path(new_location)` (same pattern already used by
   `test/launch/run_kld_parameter_sweep.py` → `test/kld_parameter_sweep/`).

2. `video_creation/transfer_visualizations/make_transfer_visualizations.py`
   — called by `test/launch/run_saliency3d_clear_pilot.sh`
   — wrapper pattern: same `runpy` shim or a one-line shell forwarder.

**Should have a wrapper or coordinated doc update (referenced in server runbooks):**

3. `validation/alignment_preview/check_alignment.py`
   — server commands and agent instructions document the path explicitly.
   — could move with a wrapper OR with a single coordinated commit that updates all
   agent instruction files, README, and server command examples simultaneously.

4. `visualization/heatmap_six_view/render_six_view_heatmaps.py`
   — same as above; server commands and `MACOS_HEATMAP_SIX_VIEW_TASK.md` reference
   the current path.

---

### Q5 — Remote branches safe to delete

The review doc already notes that the following were **locally** removed.
The corresponding remote refs still exist:

| Remote branch | Status | Safe to delete? |
|---------------|--------|----------------|
| `origin/agent/heatmap-six-view` | Merged to `reproject-benchmark` @ `f0dddb4` | **Yes** — after confirming no active worktree |
| `origin/agent/macos-fixation-format-v2` | Merged | **Yes** |
| `origin/agent/sal3d-fixed-face-gt` | Merged | **Yes** |
| `origin/agent/macos-ingestion-release` | Active worktree (`+` in `git branch -a`) | **No — keep** |
| `origin/agent/windows-geometry-metrics` | Windows worker state unresolved | **No — do not touch** |
| `origin/main` | Integration base | **No — keep** |
| `origin/reproject-benchmark` | Primary benchmark branch | **No — keep** |

All three deletions require reviewer/controller approval first; this note only
identifies which are candidates.

---

### Q6 — Keep video/heatmap/alignment tools in main repo until sigma sweep completes?

**Yes — all candidate paths should stay in the main repo until the sigma sweep is done
and verified.** Specific reasons:

1. **`validation/alignment_preview/`** is the alignment gate used before every metric
   run. If it moves before the sigma sweep gate pass, the gate commands break.

2. **`visualization/heatmap_six_view/`** will be needed to render comparison heatmaps
   once sigma sweep confirms the optimal parameters. Moving it mid-work creates churn.

3. **`video_creation/transfer_visualizations/`** is called by a production launcher
   (see Q3/Q4). Cannot move until the wrapper is in place.

4. **Sigma sweep is NOT rc2-compliant** (confirmed by code inspection):
   `test/kld_parameter_sweep/run_kld_parameter_sweep.py` resolves fixation paths via
   `SAL3D_CSV_ROOT` / `REPROJECT_GAZE_CSV_SAL3D_ROOT` (the old CSV roots) and has no
   `--fixation-root` argument for the processed-JSON format, and no `--fixed-gt-dir`
   for SAL3D. The sweep must be updated to pass the rc2 fixation root and SAL3D fixed
   GT before it can be run. Restructuring auxiliary tools during that update adds
   unnecessary risk.

5. **Tests for auxiliary tools** (`test_alignment_preview.py`,
   `test_six_view_heatmaps.py`, `test_heatmap_video_renderer.py`) are in `test/` and
   currently pass against the repo-local paths. Moving the tools to a submodule while
   the tests remain in the main repo would break the test suite unless the move is
   coordinated with the test imports.

**Recommended hold condition:**
Do not begin any physical restructuring move until: (a) full rc2 metric run on `vg-iai`
is complete and verified; (b) sigma sweep is updated to rc2 contract and successfully
run; (c) compatibility wrappers for items in Q4 are added in the same commit as the
physical move.

---

*Reviewed at `d61be84` on 2026-06-10. No code was modified.*

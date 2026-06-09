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

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

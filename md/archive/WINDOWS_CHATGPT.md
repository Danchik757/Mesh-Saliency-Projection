# Windows ChatGPT: Metrics, Aggregation, Sigma Experiments, and Research Method

## Identity

- Platform: Windows with WSL
- Branch: `agent/windows-metrics-methods`
- Server access: CPU server primarily; GPU only after coordinator approval
- Work log: append entries to the end of this file only

## Mission

Audit metric and aggregation correctness, measure sigma sensitivity, and design
one evidence-based new projection method. Do not edit participant-data loaders,
current evaluator scripts, mesh loading, alignment tools, or visualization.

Work is split into two strict phases. Complete Phase 1 and wait for coordinator
approval before starting sigma sweeps or the research method.

## Owned Paths

- `metrics/`
- metric/aggregation tests under `tests/`
- `experiments/sigma_*`
- `test/kld_parameter_sweep/`
- a new isolated research-method directory after design approval
- metrics/methodology documents assigned by the coordinator

Do not edit:

- current evaluator scripts under existing screen-space/cone implementations
- `participant_data/`
- `utils/participant_*`, `utils/mesh_*`
- `visualization/`, `gt_visualizations/`, `video_creation/`
- `test/blender_canonical/`
- another agent's coordination file
- `trash/Claude.md`, `trash/GPT.md`

## Phase 1: Metric-Run Blockers

### Milestone C1: Metrics and Aggregation Audit

Audit every metric actually emitted by benchmark scripts:

- CC;
- Spearman;
- SIM;
- KLD direction and epsilon policy;
- MSE;
- NSS;
- AUC variants.

Required checks:

- prediction/GT shape and support match;
- prediction and GT normalization matches metric definition;
- masks are applied before normalization where required;
- constant/empty/negative/NaN inputs behave explicitly;
- identical maps produce expected ideal values;
- scale invariance and monotonic-transform properties are tested where expected;
- comparison with an independent trusted implementation where possible.

Audit aggregation semantics:

- current old-CSV point weighting;
- whether participants are weighted equally;
- effect of participants with different sample counts;
- limitation that new processed fixation JSONs contain no participant IDs;
- required data-format change if participant-equal aggregation is mandatory.

Do not patch participant loaders or evaluators. Record required changes for
coordinator/owner integration.

### Milestone C2: 3DVA GT and Evaluation Protocol Audit

Verify:

- GT map/OBJ vertex count and ordering;
- original static-view GT semantics;
- CombinedGT generation and support policy;
- visible/support masking;
- whether rotating-video predictions can be compared to each GT variant;
- method output support and normalization.
- whether the current CombinedGT formula truly gives equal contribution to each
  static view, especially where support overlaps differ;
- whether any tolerated GT/visibility length mismatch preserves vertex
  correspondence rather than only truncating/padding the tail.

Produce a reproducible audit and explicit recommended reporting protocol. Do not
modify existing evaluator scripts.

Also audit the implemented cone definition: angular sigma should use
camera-to-hit depth, and any per-hit Gaussian mass dependence on local
vertex/face density must be documented with a recommendation.

After C1-C2 pass, stop and wait until the coordinator starts correct full metric
runs.

## Phase 2: Parameter Search and Research

### Milestone C3: Sigma Semantics and Sweep

1. Explain exactly what sigma means in both current methods and its unit:
   pixels, screen fraction, angle, or world-space radius.
2. Check how depth/FOV/resolution affect effective smoothing.
3. Extend the isolated sweep code without changing current evaluator logic.
4. Select representative model subsets for every dataset/track.
5. Produce tidy CSVs and plots of every relevant metric versus sigma for each
   method and dataset/track.
6. Select parameters using multiple metrics, not KLD alone.

Run on `vg-intellect-1.lab.graphicon.ru` only after coordinator review and
approval. Work only under `/mnt/ssd1/29d_kon/acm_2026`.

### Milestone C4: Evidence-Based New Method

Before implementation, write a design proposal that:

- identifies limitations of current screen-space and cone methods;
- cites relevant eye-tracking/saliency/projection research;
- defines inputs, output support, aggregation, smoothing, complexity, and
  expected failure modes;
- defines baselines and ablations;
- explains why the method should better approximate GT.

Implementation starts only after coordinator approval. Keep it isolated in a new
directory so it cannot alter current benchmark behavior.

The Windows workstation GPU may be used for local non-benchmark experiments.
Accepted metric computations remain server-only.

## Append-Only Work Log

Append new entries below. Never rewrite prior entries.
